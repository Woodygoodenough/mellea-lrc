"""Rotate CourtListener API tokens and respect their daily allowance.

CourtListener's free tier allows **125 requests per token per day**, and a
single sweep of one evaluation split needs an order of magnitude more. Rotation
is therefore not an optimization; it is the difference between one day's budget
and three.

The rule that makes rotation work is knowing when to stop. A daily cap is not a
rate to wait out: once a token's allowance is gone it stays gone until the reset
the upstream names, so the pool parks that token and moves to the next, and
reports exhaustion once every token is parked. Retrying instead is how a sweep
spends hours writing nothing but failures.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# CourtListener throttles on more than one window, and the two need opposite
# handling. It names the window in the 429 body:
#
#   "Request was throttled. Rate limit exceeded: 125/day.  Expected available in 53034 seconds."
#   "Request was throttled. Rate limit exceeded: 60/minute. Expected available in 12 seconds."
#
# The first is a spent allowance: the token is done for the day and must leave
# rotation. The second is a burst limit that clears in seconds and should simply
# be waited out. Parking a token for the second is how a pool of three empties
# itself in one burst and then refuses everything.
_DAILY_WINDOW = re.compile(r"Rate limit exceeded:\s*\d+\s*/\s*day", re.IGNORECASE)
_THROTTLED = re.compile(r"Rate limit exceeded", re.IGNORECASE)
_RETRY_SECONDS = re.compile(r"available in (\d+) seconds")
# Used when the upstream refuses without saying when it will relent.
DEFAULT_COOLDOWN_SECONDS = 3600.0
HTTP_TOO_MANY_REQUESTS = 429
# A burst refusal clears quickly; wait rather than surrendering the token.
MAX_BURST_WAIT_SECONDS = 90.0
# Longer than this and a throttle is not a short window, whatever it calls
# itself.
#
# The wording is not sufficient to tell the two apart. Classifying only by the
# literal "N/day" meant any other phrasing was read as a burst, and a burst's
# wait is capped at `MAX_BURST_WAIT_SECONDS` -- so a refusal naming hours was
# retried every ninety seconds forever. On 26 August a warming pass stored 142
# documents, roughly one token's daily allowance, and then spent 45 minutes
# making no progress at all: it was waiting out a spent allowance ninety
# seconds at a time, and would have until the day turned over.
#
# How long the upstream says to wait is what actually decides how to treat it,
# and the client already reads it that way.
BURST_HORIZON_SECONDS = 300.0


class AllTokensExhausted(RuntimeError):
    """Every token's allowance is spent, so no request can succeed right now."""

    def __init__(self, retry_after_seconds: float) -> None:
        """Record how long until the earliest token becomes usable again."""
        super().__init__(f"all CourtListener tokens are exhausted for {retry_after_seconds:.0f}s")
        self.retry_after_seconds = retry_after_seconds


@dataclass
class _Token:
    value: str
    label: str
    available_at: float = 0.0


@dataclass
class TokenPool:
    """A rotating pool of API tokens that parks each one when its quota is gone."""

    tokens: list[_Token] = field(default_factory=list)
    _cursor: int = 0

    @classmethod
    def from_environment(
        cls, environ: dict[str, str], *, prefix: str = "COURTLISTENER_API_TOKEN"
    ) -> TokenPool:
        """Collect `PREFIX`, `PREFIX_1`, `PREFIX_2`, ... in that order.

        Numbering is open-ended rather than fixed at two, so adding a token is a
        secret change and not a code change.
        """
        found: list[_Token] = []
        bare = environ.get(prefix, "").strip()
        if bare:
            found.append(_Token(value=bare, label=prefix))
        index = 1
        misses = 0
        while misses < 3:
            name = f"{prefix}_{index}"
            value = environ.get(name, "").strip()
            if value:
                found.append(_Token(value=value, label=name))
                misses = 0
            else:
                misses += 1
            index += 1
        return cls(tokens=found)

    def __post_init__(self) -> None:
        if not self.tokens:
            msg = "No CourtListener API token is configured"
            raise RuntimeError(msg)

    def acquire(self, *, now: float | None = None) -> _Token:
        """Return the next usable token, or raise if every one is parked."""
        moment = time.monotonic() if now is None else now
        for offset in range(len(self.tokens)):
            token = self.tokens[(self._cursor + offset) % len(self.tokens)]
            if token.available_at <= moment:
                self._cursor = (self._cursor + offset + 1) % len(self.tokens)
                return token
        raise AllTokensExhausted(min(token.available_at for token in self.tokens) - moment)

    def park_briefly(self, token: _Token, seconds: float, *, now: float | None = None) -> None:
        """Take a token out of rotation for a short-window throttle.

        Unlike `park`, this is not a spent allowance: the token is usable again
        in seconds. It leaves rotation so the pool's other tokens are tried
        **immediately**, because a per-minute limit is counted per token and
        the others are very likely fine. Sleeping instead idles every token for
        one token's throttle, which is what a night of warming spent 75 minutes
        doing.

        When every token is parked this way, `acquire` raises carrying the
        soonest one back, so the caller waits the shortest remaining window
        rather than the longest any single token named.
        """
        moment = time.monotonic() if now is None else now
        token.available_at = max(token.available_at, moment + seconds)

    def park(self, token: _Token, body: str, *, now: float | None = None) -> None:
        """Take a refused token out of rotation until the upstream says it is back."""
        moment = time.monotonic() if now is None else now
        token.available_at = moment + cooldown_seconds(body)
        # The body is logged because its wording is what this decision turns on,
        # and a misreading of it cost a night of warming before anyone could see
        # what the upstream had actually said.
        logger.warning(
            "parked %s for %.0fs after a quota refusal: %s",
            token.label,
            token.available_at - moment,
            body[:160],
        )

    @property
    def size(self) -> int:
        """How many tokens the pool holds."""
        return len(self.tokens)


def is_quota_refusal(status_code: int, body: str) -> bool:
    """Whether a refusal means the token's allowance is spent for a long while.

    A named per-day window counts, and so does any other throttle that says it
    will not relent for `BURST_HORIZON_SECONDS`. Deciding on the words alone
    read an hours-long refusal as a per-minute one and retried it every ninety
    seconds indefinitely; how long the upstream says to wait is the part that
    decides what to do about it.
    """
    if status_code != HTTP_TOO_MANY_REQUESTS or not _THROTTLED.search(body):
        return False
    if _DAILY_WINDOW.search(body):
        return True
    named = _RETRY_SECONDS.search(body)
    return named is not None and float(named.group(1)) > BURST_HORIZON_SECONDS


def is_burst_refusal(status_code: int, body: str) -> bool:
    """Whether a refusal is a short-window throttle worth stepping aside for.

    A per-minute limit clears in seconds, so the token keeps its place in the
    pool. Parking it for the day would empty the pool over something that is
    not an exhausted allowance at all -- which is why this is not simply the
    negation of a spent allowance: a refusal that names no wait at all is
    neither, and is left to the caller rather than guessed at.
    """
    if status_code != HTTP_TOO_MANY_REQUESTS or not _THROTTLED.search(body):
        return False
    if is_quota_refusal(status_code, body):
        return False
    named = _RETRY_SECONDS.search(body)
    return named is not None and float(named.group(1)) <= BURST_HORIZON_SECONDS


def burst_wait_seconds(body: str) -> float:
    """How long to wait out a burst refusal, bounded so a request cannot hang."""
    match = _RETRY_SECONDS.search(body)
    named = float(match.group(1)) if match else 5.0
    return min(named, MAX_BURST_WAIT_SECONDS)


def cooldown_seconds(body: str) -> float:
    """Read the reset the upstream names, or fall back to an hour."""
    match = _RETRY_SECONDS.search(body)
    if match is None:
        return DEFAULT_COOLDOWN_SECONDS
    return float(match.group(1))
