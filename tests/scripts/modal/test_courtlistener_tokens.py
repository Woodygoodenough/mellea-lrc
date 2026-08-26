"""Tests for rotating CourtListener tokens under a daily allowance."""

from __future__ import annotations

import pytest

from scripts.modal.courtlistener.tokens import (
    DEFAULT_COOLDOWN_SECONDS,
    MAX_BURST_WAIT_SECONDS,
    AllTokensExhausted,
    TokenPool,
    burst_wait_seconds,
    cooldown_seconds,
    is_burst_refusal,
    is_quota_refusal,
)

THROTTLED = "Request was throttled. Rate limit exceeded: 125/day. Expected available in 53034 seconds."
BURST = "Request was throttled. Rate limit exceeded: 60/minute. Expected available in 12 seconds."


def test_numbered_tokens_are_collected_in_order() -> None:
    """Adding a token should be a secret change, not a code change."""
    pool = TokenPool.from_environment(
        {
            "COURTLISTENER_API_TOKEN_1": "a",
            "COURTLISTENER_API_TOKEN_2": "b",
            "COURTLISTENER_API_TOKEN_3": "c",
        }
    )

    assert pool.size == 3
    assert [pool.acquire(now=0.0).value for _ in range(3)] == ["a", "b", "c"]


def test_a_gap_in_the_numbering_does_not_end_collection() -> None:
    """`_2` missing must not hide `_3`, or a token silently goes unused."""
    pool = TokenPool.from_environment({"COURTLISTENER_API_TOKEN_1": "a", "COURTLISTENER_API_TOKEN_3": "c"})

    assert pool.size == 2


def test_an_unnumbered_token_is_accepted_too() -> None:
    """The plain variable name is what a single-token deployment sets."""
    pool = TokenPool.from_environment({"COURTLISTENER_API_TOKEN": "solo"})

    assert pool.size == 1
    assert pool.acquire(now=0.0).value == "solo"


def test_no_token_configured_is_an_error_at_construction() -> None:
    """Failing at start-up beats failing on the first request."""
    with pytest.raises(RuntimeError, match="No CourtListener API token"):
        TokenPool.from_environment({})


def test_requests_rotate_across_the_pool() -> None:
    """Rotation is what turns one day's allowance into three."""
    pool = TokenPool.from_environment({"COURTLISTENER_API_TOKEN_1": "a", "COURTLISTENER_API_TOKEN_2": "b"})

    assert [pool.acquire(now=0.0).value for _ in range(4)] == ["a", "b", "a", "b"]


def test_a_parked_token_is_skipped_until_its_reset() -> None:
    """A spent daily allowance is not a rate to wait out; move to the next token."""
    pool = TokenPool.from_environment({"COURTLISTENER_API_TOKEN_1": "a", "COURTLISTENER_API_TOKEN_2": "b"})
    first = pool.acquire(now=0.0)
    pool.park(first, THROTTLED, now=0.0)

    assert pool.acquire(now=1.0).value == "b"
    assert pool.acquire(now=2.0).value == "b"


def test_a_parked_token_returns_after_the_reset_it_named() -> None:
    """The upstream says when it will relent, so honour that rather than guessing."""
    pool = TokenPool.from_environment({"COURTLISTENER_API_TOKEN_1": "a"})
    pool.park(pool.acquire(now=0.0), THROTTLED, now=0.0)

    with pytest.raises(AllTokensExhausted):
        pool.acquire(now=53033.0)

    assert pool.acquire(now=53035.0).value == "a"


def test_exhaustion_reports_when_the_earliest_token_returns() -> None:
    """A caller that knows the reset can stop instead of retrying into a wall."""
    pool = TokenPool.from_environment({"COURTLISTENER_API_TOKEN_1": "a", "COURTLISTENER_API_TOKEN_2": "b"})
    pool.park(pool.acquire(now=0.0), "Rate limit exceeded: available in 900 seconds", now=0.0)
    pool.park(pool.acquire(now=0.0), THROTTLED, now=0.0)

    with pytest.raises(AllTokensExhausted) as caught:
        pool.acquire(now=0.0)

    assert caught.value.retry_after_seconds == pytest.approx(900.0)


def test_a_daily_refusal_is_told_apart_from_an_ordinary_one() -> None:
    """Only a spent allowance parks a token; a momentary limit should be retried."""
    assert is_quota_refusal(429, THROTTLED) is True
    assert is_quota_refusal(429, "Request was throttled. Try again in 1 second.") is False
    assert is_quota_refusal(500, THROTTLED) is False


def test_a_burst_limit_is_not_a_spent_allowance() -> None:
    """CourtListener reports both windows as "Rate limit exceeded".

    Treating the per-minute one as exhaustion parks a token that is fine
    seconds later, and enough of those empty the whole pool over something that
    was never an exhausted allowance. This is the bug that made a sweep fail
    with 429s while every token still had quota.
    """
    assert is_quota_refusal(429, BURST) is False
    assert is_burst_refusal(429, BURST) is True

    assert is_burst_refusal(429, THROTTLED) is False
    assert is_quota_refusal(429, THROTTLED) is True


def test_a_burst_wait_is_bounded() -> None:
    """Honour the named wait, but never let one request hang on it."""
    assert burst_wait_seconds(BURST) == pytest.approx(12.0)
    assert burst_wait_seconds("Rate limit exceeded: 60/minute.") == pytest.approx(5.0)
    assert burst_wait_seconds("Rate limit exceeded. available in 99999 seconds") == pytest.approx(
        MAX_BURST_WAIT_SECONDS
    )


def test_the_cooldown_falls_back_when_no_reset_is_named() -> None:
    """A refusal without a reset still has to park the token for something."""
    assert cooldown_seconds(THROTTLED) == pytest.approx(53034.0)
    assert cooldown_seconds("Rate limit exceeded.") == pytest.approx(DEFAULT_COOLDOWN_SECONDS)


DAY = "Request was throttled. Rate limit exceeded: 125/day.  Expected available in 53034 seconds."
MINUTE = "Request was throttled. Rate limit exceeded: 60/minute. Expected available in 12 seconds."
LONG_UNNAMED_WINDOW = "Request was throttled. Rate limit exceeded. Expected available in 21600 seconds."
SHORT_UNNAMED_WINDOW = "Request was throttled. Rate limit exceeded. Expected available in 20 seconds."
NO_WAIT_NAMED = "Request was throttled. Rate limit exceeded."


@pytest.mark.parametrize(
    ("body", "spent", "burst"),
    [
        (DAY, True, False),
        (MINUTE, False, True),
        (LONG_UNNAMED_WINDOW, True, False),
        (SHORT_UNNAMED_WINDOW, False, True),
        (NO_WAIT_NAMED, False, False),
    ],
)
def test_a_refusal_is_classified_by_how_long_it_says_to_wait(
    body: str,
    spent: bool,
    burst: bool,
) -> None:
    """The wording alone does not separate a spent allowance from a burst limit.

    `LONG_UNNAMED_WINDOW` is the case that cost a night: six hours of refusal
    that never says "per day". Read as a burst, its wait was capped at ninety
    seconds and retried forever, so a warming pass stored one token's worth of
    documents and then made no progress for forty-five minutes.

    `NO_WAIT_NAMED` is neither, deliberately. A refusal that will not say when
    it relents is not something to park a token for the hour over, nor to retry
    in ninety seconds; it goes back to the caller as it arrived.
    """
    assert is_quota_refusal(429, body) is spent
    assert is_burst_refusal(429, body) is burst


def test_a_long_refusal_parks_for_what_it_actually_named() -> None:
    """Capping this at the burst ceiling is what made the retry loop endless."""
    pool = TokenPool.from_environment({"COURTLISTENER_API_TOKEN_1": "t1"})
    pool.park(pool.tokens[0], LONG_UNNAMED_WINDOW)

    with pytest.raises(AllTokensExhausted) as refusal:
        pool.acquire()

    assert refusal.value.retry_after_seconds > MAX_BURST_WAIT_SECONDS
