"""Fill the cache with the opinion documents the checking stage will read.

The locator probe answers one question -- is there a case at this volume and
page -- and stores the answer. Everything after that reads a different
endpoint. The pinpoint check fetches the opinion documents a cluster names, and
until those are stored too, re-running the checking stage needs a live service
and a daily allowance, which is what has kept its figures stale.

Sizing, over the locators the probe resolved on this corpus:

* 668 citations resolve to exactly one case
* those cases name **1,172 opinion documents**, of which 1,068 are distinct
* 467 clusters carry a single opinion; 201 carry three or more

So this is roughly three nights of allowance, and once done the checking stage
runs offline and reproducibly.

Two things it deliberately does not do.

**It does not decide anything.** It reads documents so they are stored, and
writes no verdict. What the stored documents mean is the checking stage's
business, and keeping the two apart is what lets this run unattended.

**It does not stop at the first opinion of a cluster.** The checking stage
prefers the opinion of the Court and stops when it finds a unanimous one, so a
run against a warm cache reads fewer documents than this fetches. Warming all
of them is the point: the aim is that any later run finds what it needs
already there, including one that reaches an opinion this one's ordering
happened to skip.

Progress lives in the cache behind the proxy, not here, so an interrupted run
loses nothing and a re-run costs only the requests it has not already made.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from evaluations.lephantomcite.locator_probe import (
    SHORT_REFUSAL_SECONDS,
    DailyQuotaExhausted,
    _refusal_seconds,
    _Throttle,
    is_quota_refusal_for,
    parse_locator,
)
from mellea_lrc.courtlistener import CourtListenerError
from mellea_lrc.courtlistener.client import CourtListenerClient, CourtListenerConfig

logger = logging.getLogger(__name__)

MIN_REQUEST_INTERVAL_SECONDS = 2.0


def opinion_ids_for(dataset: Path, client: CourtListenerClient) -> list[str]:
    """Every opinion document the resolved citations in the dataset name.

    Reads the locator answers back out of the cache, so it costs nothing when
    the probe has already run and is the reason this can be sized before it is
    spent.
    """
    locators = set()
    for line in dataset.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        for cited in json.loads(line).get("citations_in_segment") or []:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                parts = parse_locator(str(cited))
            if parts is not None:
                locators.add(parts.key)

    ordered: list[str] = []
    seen: set[str] = set()
    for key in sorted(locators):
        try:
            lookup = client.lookup_citation(*key)
        except CourtListenerError:
            # The locator was never answered, so there is nothing to warm for
            # it. Run the probe first; this is not the place to fix that.
            continue
        if len(lookup.clusters) != 1:
            continue
        for opinion_id in lookup.clusters[0].sub_opinion_ids or ():
            if opinion_id not in seen:
                seen.add(opinion_id)
                ordered.append(opinion_id)
    return ordered


def warm(ids: list[str], client: CourtListenerClient) -> dict[str, int]:
    """Read each opinion once so the cache holds it. Returns what happened."""
    counts = {"stored": 0, "failed": 0, "remaining": 0}
    throttle = _Throttle(MIN_REQUEST_INTERVAL_SECONDS)
    for index, opinion_id in enumerate(ids):
        throttle.wait()
        try:
            client.get_opinion(opinion_id)
        except CourtListenerError as error:
            detail = str(error.upstream_detail)
            waiting = _refusal_seconds(detail)
            if is_quota_refusal_for(detail):
                counts["remaining"] = len(ids) - index
                logger.error(
                    "daily allowance spent after %s of %s opinions: %s",
                    index,
                    len(ids),
                    detail[:120],
                )
                raise DailyQuotaExhausted(detail[:120]) from error
            if waiting is not None and waiting < SHORT_REFUSAL_SECONDS:
                logger.info("allowance returns in %ss; waiting", waiting)
                time.sleep(waiting + 5)
                continue
            counts["failed"] += 1
            logger.warning("could not read opinion %s: %s", opinion_id, error.message)
            continue
        counts["stored"] += 1
    return counts


def main() -> None:
    """Warm the opinion cache for one dataset."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="path to eval.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many documents")
    arguments = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = CourtListenerClient(CourtListenerConfig.from_env())

    ids = opinion_ids_for(arguments.dataset, client)
    if arguments.limit is not None:
        ids = ids[: arguments.limit]
    logger.info("%s distinct opinion documents to warm", len(ids))

    try:
        counts = warm(ids, client)
    except DailyQuotaExhausted as exhausted:
        logger.error("stopping; the cache keeps every document that landed: %s", exhausted.detail)
        sys.exit(0)
    logger.info(
        "warmed %s, could not read %s, remaining %s",
        counts["stored"],
        counts["failed"],
        counts["remaining"],
    )


if __name__ == "__main__":
    main()
