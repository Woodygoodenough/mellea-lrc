"""Evaluate extracted citation identifiers against a frozen JSONL bench."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_DOCKET_PREFIX = re.compile(r"^(no|case|civilaction|civ|cv)+")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read one JSON object per nonblank line."""
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as error:
        msg = f"{path}: invalid JSONL: {error}"
        raise ValueError(msg) from error


def _normalize(value: str) -> str:
    """Reduce a string to the characters that carry its identity."""
    return _NON_ALPHANUMERIC.sub("", value.lower())


def identity(record: dict[str, Any], *, source: str) -> tuple[str, str]:
    """Return the kind and normalized identifier of one occurrence.

    A record is a locator when it carries all three parts of one, and a docket
    otherwise. A span alone identifies nothing and cannot be matched.
    """
    volume, reporter, page = record.get("volume"), record.get("reporter"), record.get("page")
    if volume and reporter and page:
        return ("locator", f"{_normalize(str(volume))}|{_normalize(str(reporter))}|{_normalize(str(page))}")
    text = record.get("matched_text")
    if not isinstance(text, str) or not _normalize(text):
        raise ValueError(
            f"{source} {record.get('document')}: an occurrence needs either volume, reporter and "
            f"page, or a matched_text to identify it"
        )
    # "No.", "Case No." and the like name no part of the docket itself.
    return ("docket", _DOCKET_PREFIX.sub("", _normalize(text)))


def court_tokens(record: dict[str, Any]) -> set[str]:
    """Return the court as written and as resolved, so either form can match."""
    return {_normalize(str(value)) for key in ("court", "court_id") if (value := record.get(key))}


def _require_occurrence(record: dict[str, Any], *, source: str) -> None:
    """Validate the occurrence fields shared by bench and run artifacts."""
    document = record.get("document")
    if not isinstance(document, str) or not document:
        raise ValueError(f"{source}: missing non-empty document")
    span = record.get("span")
    if (
        not isinstance(span, dict)
        or not isinstance(span.get("start"), int)
        or not isinstance(span.get("end"), int)
    ):
        raise ValueError(f"{source} {document}: span must contain integer start and end")
    if span["start"] < 0 or span["end"] <= span["start"]:
        raise ValueError(f"{source} {document}: span must be a non-empty half-open span")


def _prepare(records: list[dict[str, Any]], *, source: str) -> list[dict[str, Any]]:
    """Validate records and attach what matching needs."""
    seen: set[tuple[str, int, int]] = set()
    for record in records:
        _require_occurrence(record, source=source)
        key = (record["document"], record["span"]["start"], record["span"]["end"])
        if key in seen:
            raise ValueError(f"{source}: duplicate occurrence {key}")
        seen.add(key)
        record["_identity"] = identity(record, source=source)
        record["_courts"] = court_tokens(record)
    return sorted(records, key=lambda r: (r["document"], r["span"]["start"]))


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return whether two spans share at least one character."""
    a, b = left["span"], right["span"]
    return a["start"] < b["end"] and b["start"] < a["end"]


def _same_court(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    """Return whether a docket prediction names the court the benchmark does."""
    if expected["_identity"][0] != "docket":
        return True
    return bool(expected["_courts"] & observed["_courts"])


def _matches(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    """Return whether a prediction reports the benchmark's occurrence."""
    return (
        expected["document"] == observed["document"]
        and expected["_identity"] == observed["_identity"]
        and _same_court(expected, observed)
        and _overlaps(expected, observed)
    )


def evaluate(
    benchmark_path: Path,
    artifact_path: Path,
    *,
    kinds: frozenset[str] | None = None,
) -> tuple[Counter[str], list[dict[str, Any]]]:
    """Score one run artifact and return counts plus every disagreeing occurrence.

    ``kinds`` restricts the task to occurrences of those kinds, on both sides.
    Restricting it is not the same as ignoring the rest: a prediction of an
    excluded kind is dropped rather than counted as a false positive, because
    the system is no longer being asked that question.

    This matters for the two kinds this benchmark holds. A ``locator`` is a
    volume, reporter and page, which is what a citation tokenizer exists to
    find. A ``docket`` is a docket number, which eyecite does not model at all,
    so an eyecite-based arm scores zero on every one of them by construction.
    Leaving the eleven docket records in the denominator lowers every such
    arm's recall by a constant that says nothing about the arm.
    """
    expected = _prepare(_read_jsonl(benchmark_path), source="benchmark")
    observed = _prepare(_read_jsonl(artifact_path), source="artifact")
    if kinds is not None:
        expected = [record for record in expected if identity(record, source="benchmark")[0] in kinds]
        observed = [record for record in observed if identity(record, source="artifact")[0] in kinds]
    if not expected:
        raise ValueError("benchmark has no occurrences")

    # Each benchmark occurrence is claimed once, so one citation reported twice
    # earns one true positive and one false positive.
    unmatched = list(expected)
    matched: list[dict[str, Any]] = []
    spurious: list[dict[str, Any]] = []
    for prediction in observed:
        hit = next((c for c in unmatched if _matches(c, prediction)), None)
        if hit is None:
            spurious.append(prediction)
        else:
            unmatched.remove(hit)
            matched.append(prediction)

    counts = Counter(
        {
            "expected": len(expected),
            "predicted": len(observed),
            "true_positive": len(matched),
            "false_positive": len(spurious),
            "false_negative": len(unmatched),
        }
    )
    disagreements = [
        {"reason": reason, "occurrence": {k: v for k, v in record.items() if not k.startswith("_")}}
        for reason, records in (("false_negative", unmatched), ("false_positive", spurious))
        for record in records
    ]
    return counts, disagreements


def _kind_breakdown(benchmark_path: Path, artifact_path: Path) -> str:
    """Score each kind on its own, so a headline number names its own task."""
    all_kinds = sorted({identity(record, source="benchmark")[0] for record in _read_jsonl(benchmark_path)})
    rows = ["| Kind | Expected | True positives | Precision | Recall |", "|---|---:|---:|---:|---:|"]
    for kind in all_kinds:
        counts, _ = evaluate(benchmark_path, artifact_path, kinds=frozenset({kind}))
        true_positive = counts["true_positive"]
        precision = true_positive / counts["predicted"] if counts["predicted"] else 0.0
        recall = true_positive / counts["expected"] if counts["expected"] else 0.0
        rows.append(f"| {kind} | {counts['expected']} | {true_positive} | {precision:.1%} | {recall:.1%} |")
    return "\n".join(rows)


def _format(counts: Counter[str]) -> str:
    """Render precision, recall, and F1 over matched occurrences."""
    true_positive = counts["true_positive"]
    precision = true_positive / counts["predicted"] if counts["predicted"] else 0.0
    recall = true_positive / counts["expected"] if counts["expected"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| Expected occurrences | {counts['expected']} |",
            f"| Predicted occurrences | {counts['predicted']} |",
            f"| True positives | {true_positive} |",
            f"| False positives | {counts['false_positive']} |",
            f"| False negatives | {counts['false_negative']} |",
            f"| Precision | {precision:.1%} |",
            f"| Recall | {recall:.1%} |",
            f"| F1 | {f1:.1%} |",
        ]
    )


def main() -> None:
    """Run the command-line evaluator."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True, help="Extraction bench JSONL file.")
    parser.add_argument("--artifact", type=Path, required=True, help="One JSONL run artifact.")
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation-result"))
    parser.add_argument(
        "--kind",
        action="append",
        help=(
            "Score only this occurrence kind; repeatable. Predictions of other "
            "kinds are dropped rather than counted against the run."
        ),
    )
    args = parser.parse_args()

    kinds = frozenset(args.kind) if args.kind else None
    counts, disagreements = evaluate(args.benchmark, args.artifact, kinds=kinds)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "non_agreements.json"
    output.write_text(json.dumps(disagreements, indent=2) + "\n", encoding="utf-8")
    if kinds is not None:
        print(f"Scoring only: {', '.join(sorted(kinds))}\n")
    print(_format(counts))
    if kinds is None:
        print()
        print(_kind_breakdown(args.benchmark, args.artifact))
    print(f"Details: {output}")


if __name__ == "__main__":
    main()
