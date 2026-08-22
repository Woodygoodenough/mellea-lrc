"""List every occurrence the arms do not agree on, for a person to settle.

A metric is only comparatively honest if the gold set is not quietly wrong in
one arm's favour. The cheapest guard against that is disagreement: wherever two
arms differ about a span, one of them is wrong, or the gold is. Those are the
only places worth a person's time, and there are few of them -- on
false-citation-bench v2 the four model-free arms disagree about 43 occurrences
out of 583, and most collapse into a handful of causes.

The check runs on predictions alone, so it also catches the case a
gold-versus-arm comparison cannot: a citation every arm finds and the gold does
not have. That one never appears as a false negative, because the gold has
nothing to miss; it appears as an identical false positive in every arm, which
is the signature of an annotation gap rather than an extraction fault.

Usage::

    uv run python -m evaluations.extraction.disagreements \
        --benchmark data/false-citation-bench-v2/derived/extraction.jsonl \
        --artifact eyecite=runs/eyecite.jsonl \
        --artifact production=runs/production.jsonl \
        --kind locator
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluations.extraction.evaluate import identity


def _read(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _key(record: dict[str, Any]) -> tuple[str, int, int]:
    """Identify an occurrence by where it sits, which is what arms disagree about."""
    return (record["document"], record["span"]["start"], record["span"]["end"])


def _kind_of(record: dict[str, Any], *, source: str) -> str:
    """The occurrence kind, inferred as the evaluator infers it.

    A run artifact does not carry a `kind` field -- an arm reports what it
    found, not which task it was being scored on -- so filtering on one read
    off the record drops every prediction and reports the whole benchmark as
    unfound. Asking the evaluator keeps the two in step.
    """
    return identity(record, source=source)[0]


def collect(benchmark: Path, artifacts: dict[str, Path], *, kind: str | None) -> list[dict[str, Any]]:
    """Every occurrence not predicted by every arm, or not present in the gold."""
    gold = {_key(r): r for r in _read(benchmark) if kind is None or _kind_of(r, source="benchmark") == kind}
    predicted: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    text: dict[tuple[str, int, int], str] = {}
    for arm, path in artifacts.items():
        for record in _read(path):
            if kind is not None and _kind_of(record, source="artifact") != kind:
                continue
            predicted[_key(record)].add(arm)
            text.setdefault(_key(record), record.get("matched_text", ""))

    everyone = set(artifacts)
    rows = []
    for occurrence in sorted(set(predicted) | set(gold)):
        found_by = predicted.get(occurrence, set())
        in_gold = occurrence in gold
        if found_by == everyone and in_gold:
            continue
        rows.append(
            {
                "document": occurrence[0],
                "span": {"start": occurrence[1], "end": occurrence[2]},
                "matched_text": text.get(occurrence) or gold[occurrence]["matched_text"],
                "in_gold": in_gold,
                "found_by": sorted(found_by),
                "missed_by": sorted(everyone - found_by),
                "verdict": _verdict(found_by, everyone, in_gold=in_gold),
            }
        )
    return rows


def _verdict(found_by: set[str], everyone: set[str], *, in_gold: bool) -> str:
    """What kind of question this occurrence poses."""
    if found_by == everyone and not in_gold:
        return "every arm finds it, the gold does not have it — check the page"
    if not found_by and in_gold:
        return "no arm finds it, the gold has it — check the page"
    if in_gold:
        return "some arms miss a gold occurrence — an extraction gap"
    return "some arms invent an occurrence the gold lacks — check the page"


def main() -> None:
    """Write the review list."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--artifact", action="append", required=True, help="name=path, repeatable")
    parser.add_argument("--kind", default=None)
    parser.add_argument("--output", type=Path, default=Path("disagreements.json"))
    arguments = parser.parse_args()

    artifacts = {}
    for entry in arguments.artifact:
        name, _, path = entry.partition("=")
        artifacts[name] = Path(path)

    rows = collect(arguments.benchmark, artifacts, kind=arguments.kind)
    arguments.output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["verdict"]] += 1
    print(f"occurrences needing a decision: {len(rows)}")
    for verdict, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"  {count:4}  {verdict}")
    print(f"Details: {arguments.output}")


if __name__ == "__main__":
    main()
