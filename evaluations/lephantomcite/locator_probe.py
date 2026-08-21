"""Resolve every LePhantomCite citation against CourtListener, and nothing more.

This isolates the identity layer. No model is called: each citation is parsed
to volume, reporter and page, looked up once, and classified by what the lookup
alone establishes. What the probe measures is how much of the benchmark is
decidable before any semantic judgement is attempted, and at what cost in
abstention.

The outcome vocabulary is the point. A lookup can fail in two ways that a
binary benchmark records identically:

- **refuted** -- the reporter series named does not exist. `446 Cal. Rptr. 4th`
  is not a reporter, so no volume or page of it can be. This is established
  offline against the reporter database, before any request is sent, and it is
  positive evidence of fabrication rather than an absence.
- **unresolved** -- the reporter is real and the archive holds no case at that
  volume and page. The citation may be sound and simply unindexed, so the only
  honest answer is that the lookup could not decide.

Collapsing the second into a defect verdict is the error this project exists to
avoid, and the rate at which it would fire is one of the numbers this probe
reports.
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import TYPE_CHECKING

from reporters_db import EDITIONS, VARIATIONS_ONLY

from mellea_lrc.core.citations import FullCaseCitation, ShortCaseCitation
from mellea_lrc.courtlistener import CourtListenerClient, CourtListenerError
from mellea_lrc.extraction import extract_from_plain_text

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from mellea_lrc.courtlistener.protocols import CourtListenerServiceClient

logger = logging.getLogger(__name__)

# CourtListener answers an unknown reporter abbreviation with a 400 and says so.
# A 404 or an empty cluster list means the series is real and the case is not
# in the archive, which is a different finding.
_UNKNOWN_REPORTER_STATUS = 400

# CourtListener limits this endpoint at a steady rate, and burst-then-back-off
# is the wrong shape for that: a sweep sends as fast as it can, is refused, waits,
# and retries into a window its own retries are still filling. A full pass of the
# eval split spent four hours that way and answered nothing.
#
# Pacing fixes it. Requests are spaced by a fixed minimum interval below the
# limit, so the sweep runs at the rate the service allows instead of discovering
# that rate by being refused. Backoff stays for the occasional refusal, but it
# should now be rare rather than the steady state.
MIN_REQUEST_INTERVAL_SECONDS = 2.0
MAX_ATTEMPTS = 5
RETRY_BASE_SECONDS = 5.0
MAX_RETRY_SECONDS = 60.0
# One worker, because the throttle sets the pace and concurrency would only
# bunch requests back up against the limit.
DEFAULT_MAX_WORKERS = 1

# Serial publications that are real but are not case reporters. The project
# validates case citations, so a citation to one of these is out of scope
# rather than fabricated -- reporting `80 Fed. Reg. 64,545` as a defect would
# be exactly the false positive this vocabulary exists to prevent. They need
# naming because eyecite types their short forms (`80 Fed. Reg. at 64,545`) as
# short case citations, so they reach a lookup that then rejects the reporter.
NON_CASE_SOURCES = frozenset({"fedreg", "congrec", "cfr", "usc", "stat"})

# A citation that states volume, some reporter tokens, and a page, without the
# reporter being a real series. Extraction refuses such a string, so it never
# reaches a lookup, and the refusal is itself the finding.
_LOCATOR_SHAPE = re.compile(r"\b\d+\s+(?P<reporter>[A-Za-z][A-Za-z0-9.'’ ]*?)\s+(?:at\s+)?\d+\b")
_NON_ALNUM = re.compile(r"[^a-z0-9]")
# Variations as well as canonical editions: `Fed. Appx.` is how a filing often
# spells `F. App'x`, and calling a real reporter fabricated because a brief used
# its common abbreviation would be the worst error this check could make.
_KNOWN_REPORTERS = {_NON_ALNUM.sub("", name.lower()) for name in (*EDITIONS, *VARIATIONS_ONLY)}


class LookupOutcome(str, Enum):
    """What one exact locator lookup established, and only that."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    REFUTED = "refuted"
    UNRESOLVED = "unresolved"
    OUT_OF_SCOPE = "out_of_scope"
    UNPARSED = "unparsed"
    FAILED = "failed"


class _Throttle:
    """Space requests by a minimum interval, shared across worker threads."""

    def __init__(self, interval_seconds: float) -> None:
        self.interval = interval_seconds
        self._lock = Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        """Block until the next request may be sent, then claim that slot."""
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.interval
        if delay:
            time.sleep(delay)


@dataclass(frozen=True, slots=True)
class LocatorParts:
    """The three parts of a reporter locator, as extraction read them."""

    volume: str
    reporter: str
    page: str

    @property
    def key(self) -> tuple[str, str, str]:
        """A hashable identity for deduplicating lookups across excerpts."""
        return (self.volume, self.reporter, self.page)


@dataclass(frozen=True, slots=True)
class LookupResult:
    """One locator, what the lookup said, and how many clusters came back."""

    parts: LocatorParts | None
    outcome: LookupOutcome
    cluster_count: int = 0
    detail: str | None = None


def parse_locator(cited_text: str) -> LocatorParts | None:
    """Read volume, reporter and page out of a citation string via extraction.

    The benchmark's citation strings are run through the project's own
    extractor rather than a bespoke parser, so a locator is read here exactly
    as it would be read in a document.
    """
    document = extract_from_plain_text(cited_text)
    for item in document.citations:
        citation = item.citation
        if not isinstance(citation, FullCaseCitation | ShortCaseCitation):
            continue
        volume, reporter, page = citation.volume, citation.reporter, citation.page
        if volume and reporter and page:
            return LocatorParts(volume=volume, reporter=reporter, page=page)
    return None


def probe_locators(
    cited_texts: Iterable[str],
    *,
    client: CourtListenerServiceClient | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    checkpoint: Path | None = None,
    request_interval: float = MIN_REQUEST_INTERVAL_SECONDS,
    retry_base: float = RETRY_BASE_SECONDS,
) -> dict[str, LookupResult]:
    """Look up each distinct citation string once and return its result by string.

    Lookups are deduplicated on the parsed locator, so a citation repeated
    across excerpts costs one request. Results are keyed by the original string
    because that is what the benchmark's labels are keyed on.

    CourtListener rate-limits this endpoint hard enough that a full split takes
    hours, so a `checkpoint` path is read back before starting and appended to
    as each lookup lands. An interrupted run resumes rather than restarting, and
    the results of one that never finished are still readable.
    """
    service = client or CourtListenerClient()
    texts = list(dict.fromkeys(cited_texts))
    parsed = {text: parse_locator(text) for text in texts}

    distinct: dict[tuple[str, str, str], LocatorParts] = {}
    for parts in parsed.values():
        if parts is not None:
            distinct.setdefault(parts.key, parts)

    done = _read_checkpoint(checkpoint) if checkpoint is not None else {}
    pending = {key: parts for key, parts in distinct.items() if key not in done}
    logger.info("%d distinct locators, %d already checkpointed", len(distinct), len(distinct) - len(pending))

    lock = Lock()
    throttle = _Throttle(request_interval)

    def run(parts: LocatorParts) -> tuple[tuple[str, str, str], LookupResult]:
        result = _lookup_one(service, parts, throttle=throttle, retry_base=retry_base)
        if checkpoint is not None:
            with lock:
                _append_checkpoint(checkpoint, parts, result)
        return (parts.key, result)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for key, result in pool.map(run, pending.values()):
            done[key] = result

    return {
        text: (
            done.get(parts.key, LookupResult(parts=parts, outcome=LookupOutcome.FAILED, detail="not run"))
            if parts is not None
            else _unparsed_result(text)
        )
        for text, parts in parsed.items()
    }


def _read_checkpoint(path: Path) -> dict[tuple[str, str, str], LookupResult]:
    """Read completed lookups, treating a failure as unfinished rather than done.

    A `failed` row is a retry budget that ran out against a rate limit, not an
    answer about a citation. Resuming past it would freeze infrastructure noise
    into the result, so those keys are dropped and the next run retries them.
    A later successful row for the same locator supersedes an earlier failure.
    """
    if not path.exists():
        return {}
    done: dict[tuple[str, str, str], LookupResult] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        parts = LocatorParts(volume=row["volume"], reporter=row["reporter"], page=row["page"])
        outcome = LookupOutcome(row["outcome"])
        if outcome is LookupOutcome.FAILED:
            done.pop(parts.key, None)
            continue
        done[parts.key] = LookupResult(
            parts=parts,
            outcome=outcome,
            cluster_count=row["cluster_count"],
            detail=row["detail"],
        )
    return done


def _append_checkpoint(path: Path, parts: LocatorParts, result: LookupResult) -> None:
    row = {
        "volume": parts.volume,
        "reporter": parts.reporter,
        "page": parts.page,
        "outcome": result.outcome.value,
        "cluster_count": result.cluster_count,
        "detail": result.detail,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def is_non_case_source(reporter: str) -> bool:
    """Whether the reporter names a real publication that is not a case reporter."""
    return _NON_ALNUM.sub("", reporter.lower()) in NON_CASE_SOURCES


def names_no_real_reporter(cited_text: str) -> bool:
    """Whether the string is shaped like a locator but names no real reporter series.

    A citation stating `446 Cal. Rptr. 4th 183` has a volume, a page and a
    reporter that does not exist. Extraction declines it for that reason, so the
    decline carries a finding rather than a failure.
    """
    for match in _LOCATOR_SHAPE.finditer(cited_text):
        if _NON_ALNUM.sub("", match["reporter"].lower()) in _KNOWN_REPORTERS:
            return False
    return bool(_LOCATOR_SHAPE.search(cited_text))


def summarize(results: Sequence[LookupResult]) -> dict[str, int]:
    """Count results by outcome, with every outcome present even at zero."""
    counts = dict.fromkeys((outcome.value for outcome in LookupOutcome), 0)
    for result in results:
        counts[result.outcome.value] += 1
    return counts


def _unparsed_result(cited_text: str) -> LookupResult:
    if names_no_real_reporter(cited_text):
        return LookupResult(
            parts=None,
            outcome=LookupOutcome.REFUTED,
            detail="no such reporter series",
        )
    return LookupResult(parts=None, outcome=LookupOutcome.UNPARSED)


def _lookup_one(
    client: CourtListenerServiceClient,
    parts: LocatorParts,
    *,
    attempts: int = MAX_ATTEMPTS,
    throttle: _Throttle | None = None,
    retry_base: float = RETRY_BASE_SECONDS,
) -> LookupResult:
    response = None
    for attempt in range(attempts):
        if throttle is not None:
            throttle.wait()
        try:
            response = client.lookup_citation(parts.volume, parts.reporter, parts.page)
            break
        except CourtListenerError as error:
            if not error.retryable or attempt == attempts - 1:
                logger.warning("lookup failed for %s: %s", parts.key, error.message)
                return LookupResult(parts=parts, outcome=LookupOutcome.FAILED, detail=error.failure_type)
            delay = min(retry_base * (2**attempt), MAX_RETRY_SECONDS)
            logger.info("retrying %s in %.1fs after %s", parts.key, delay, error.failure_type)
            time.sleep(delay)
    if response is None:  # pragma: no cover - the loop either breaks or returns
        return LookupResult(parts=parts, outcome=LookupOutcome.FAILED, detail="no response")

    clusters = len(response.clusters)
    if clusters == 1:
        return LookupResult(parts=parts, outcome=LookupOutcome.RESOLVED, cluster_count=1)
    if clusters > 1:
        return LookupResult(parts=parts, outcome=LookupOutcome.AMBIGUOUS, cluster_count=clusters)
    if response.status == _UNKNOWN_REPORTER_STATUS:
        outcome = LookupOutcome.OUT_OF_SCOPE if is_non_case_source(parts.reporter) else LookupOutcome.REFUTED
        return LookupResult(parts=parts, outcome=outcome, detail=response.error_message)
    return LookupResult(parts=parts, outcome=LookupOutcome.UNRESOLVED, detail=response.error_message)
