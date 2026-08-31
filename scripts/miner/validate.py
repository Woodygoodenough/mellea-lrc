"""Validate promoted filings without throwing most of the run away.

`evaluations/validation/run_mellea_lrc.py` treats a CourtListener refusal as a
failed node and carries on. Over the mined corpus that meant 833 of 1,769
citations were refused with 429 and never checked: the run still took its full
wall clock and its full model spend, and produced a verdict for 236 citations.

A refusal is not an answer. This waits it out and asks again, the way the
warming and mining jobs do -- CourtListener throttles on two windows, and the
short one clears in about thirty seconds, so a client that treats both as fatal
discards most of a day's allowance while appearing to work.

A citation whose lookup is refused after the wait cap is left unvalidated
rather than recorded as failed, so a later run picks it up instead of inheriting
a verdict that was never reached.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import time

from mellea_lrc.courtlistener import CourtListenerClient, CourtListenerError
from mellea_lrc.extraction import extract_from_plain_text
from mellea_lrc.llm import start_mellea_session_from_env
from mellea_lrc.serialization.validated_document import serialize_validated_document
from mellea_lrc.validation import validate_document

CORPUS = pathlib.Path("local/mined-corpus")
SERIALIZED = pathlib.Path("local/mined-serialized")
MAX_WAIT_SECONDS = 2400.0


class AllowanceSpent(RuntimeError):
    """The daily allowance is gone, so no further document can be validated."""


class PatientClient(CourtListenerClient):
    """A client that waits out a refusal instead of reporting it as a failure."""

    def lookup_citation(self, volume: str, reporter: str, page: str):  # type: ignore[override]
        while True:
            try:
                return super().lookup_citation(volume, reporter, page)
            except CourtListenerError as refusal:
                detail = refusal.upstream_detail if isinstance(refusal.upstream_detail, dict) else {}
                wait = detail.get("retry_after_seconds")
                if wait is None:
                    raise
                if float(wait) > MAX_WAIT_SECONDS:
                    # A wait measured in hours is the daily allowance, not a
                    # burst. Continuing writes a run for every remaining
                    # document in which nothing was checked, and those look
                    # like results. Stop instead and leave them for later.
                    raise AllowanceSpent(f"allowance returns in {float(wait) / 3600:.1f}h")
                print(f"    allowance refused, waiting {float(wait) / 60:.1f}min", flush=True)
                time.sleep(float(wait) + 2)


def unvalidated(labelled_first: bool = True) -> list[pathlib.Path]:
    """Promoted documents with no serialized run yet, those carrying a label first."""
    done = {path.stem for path in SERIALIZED.glob("*.json")}
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    labelled = {row["document"] for row in manifest if row.get("court_named_citations")}
    todo = [path for path in sorted(CORPUS.glob("*.txt")) if path.stem not in done]
    if not labelled_first:
        return todo
    return ([p for p in todo if p.stem in labelled]
            + [p for p in todo if p.stem not in labelled])


async def run(paths: list[pathlib.Path]) -> None:
    client = PatientClient()
    session = start_mellea_session_from_env()
    for path in paths:
        try:
            validated = await validate_document(
                extract_from_plain_text(path.read_text(encoding="utf-8"), source_path=path.stem),
                client=client, session=session)
        except AllowanceSpent as spent:
            print(f"  stopping: {spent}. {len(paths) - paths.index(path)} documents left for later.")
            return
        serialized = serialize_validated_document(validated)
        refused = sum(1 for citation in serialized["citations"]
                      for node in citation.get("nodes", [])
                      if node.get("status") == "failed")
        (SERIALIZED / f"{path.stem}.json").write_text(json.dumps(serialized, indent=2))
        print(f"  {path.stem:<18} {len(validated.citations):>4} citations"
              f"  {refused:>4} still refused", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    SERIALIZED.mkdir(parents=True, exist_ok=True)
    todo = unvalidated()
    print(f"{len(todo)} documents unvalidated; running {min(args.limit, len(todo))}")
    asyncio.run(run(todo[:args.limit]))
