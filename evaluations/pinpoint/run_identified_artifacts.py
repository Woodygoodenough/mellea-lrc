"""Run the pinpoint stage over an identity run and score it against validation-v2.0.

    uv run python -m evaluations.pinpoint.run_identified_artifacts data/runs/extraction-v2.0-identified
    uv run python -m evaluations.pinpoint.run_identified_artifacts data/runs/extraction-v2.0-identified --only 023

Writes `<run>-pinpointed/documents/*.json` (the identified artifacts with the
pinpoint nodes appended), `summary.txt`, `findings.md` (every pin cite called
false, with the filing's words beside the page's), `manifest.json`, and
`scores.txt` against the WRONG_PINCITE entries of `data/validation-v2.0`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from evaluations.identity.run_extraction_artifacts import BudgetedClient, MissBudgetExhausted
from mellea_lrc.courtlistener import CourtListenerClient
from mellea_lrc.serialization import serialize_identified_document
from mellea_lrc.serialization.identified_document import deserialize_identified_document
from mellea_lrc.validation.pinpoint import pinpoint_document
from mellea_lrc.validation.types import (
    MelleaPinpointReadingNode,
    PageRetrievalNode,
    PinpointResolutionNode,
    PinpointScopeNode,
    ValidationNodeStatus,
)

ANNOTATIONS = Path("data/validation-v2.0/annotations.json")


def _commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run(run_dir: Path, out_dir: Path, *, miss_budget: int, only: str | None, limit: int | None) -> int:
    client = BudgetedClient(CourtListenerClient(), miss_budget=miss_budget)
    (out_dir / "documents").mkdir(parents=True, exist_ok=True)
    scopes: Counter[str] = Counter()
    pages: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    readings = Counter()
    findings: list[str] = []
    per_document: dict[str, dict[str, object]] = {}
    paths = sorted((run_dir / "documents").glob("*.json"))
    if only:
        paths = [p for p in paths if only in p.name]
    paths = paths[:limit]
    stopped = None
    for path in paths:
        identified = deserialize_identified_document(json.loads(path.read_text(encoding="utf-8")))
        print(f"{path.stem[:60]:60} {len(identified.records):4} citations", file=sys.stderr)
        try:
            asyncio.run(pinpoint_document(identified, client=client))
        except MissBudgetExhausted as exc:
            stopped = str(exc)
            break
        (out_dir / "documents" / path.name).write_text(
            json.dumps(serialize_identified_document(identified), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        doc_outcomes: dict[str, dict[str, object]] = {}
        text = identified.source.text
        for record in identified.records:
            for node in record.trace.nodes:
                if isinstance(node, PinpointScopeNode):
                    scopes[node.outcome.value] += 1
                elif isinstance(node, PageRetrievalNode):
                    pages[node.outcome.value] += 1
                elif isinstance(node, MelleaPinpointReadingNode):
                    readings[(node.status.value, node.outcome.value if node.outcome else None)] += 1
                elif isinstance(node, PinpointResolutionNode):
                    outcomes[node.outcome.value] += 1
                    doc_outcomes[record.citation_id] = {
                        "authority_id": record.authority_id,
                        "locator_start": record.source.locator_span.start,
                        "full_start": record.source.full_span.start,
                        "outcome": node.outcome.value,
                        "false": node.false_pin_cite,
                        "misquoted": node.misquoted,
                        "kind": node.defect_kind,
                        "pin": node.pin_cite,
                    }
                    if node.false_pin_cite or node.misquoted:
                        findings.append(_finding(path.stem, record, node, text))
        per_document[path.name] = doc_outcomes
    summary = "\n".join(
        [
            f"{len(per_document)} documents",
            f"{client.requests} requests, {client.misses} not served from cache",
            "scope:",
            *(f"  {k:28} {v:4}" for k, v in scopes.most_common()),
            "page retrieval:",
            *(f"  {k:28} {v:4}" for k, v in pages.most_common()),
            "readings (status, relation):",
            *(f"  {k!s:40} {v:4}" for k, v in readings.most_common()),
            "outcomes:",
            *(f"  {k:28} {v:4}" for k, v in outcomes.most_common()),
            *([f"stopped: {stopped}"] if stopped else []),
        ]
    )
    (out_dir / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    (out_dir / "findings.md").write_text(
        "# Pin cites called false\n\n" + "\n\n".join(findings) + "\n", encoding="utf-8"
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "pinpoint_run",
                "source": str(run_dir),
                "produced_by": "evaluations/pinpoint/run_identified_artifacts.py",
                "commit": _commit(),
                "written": datetime.now(UTC).isoformat(timespec="seconds"),
                "documents": len(per_document),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(summary)
    if ANNOTATIONS.exists():
        scores = score(per_document)
        (out_dir / "scores.txt").write_text(scores + "\n", encoding="utf-8")
        print(scores)
    return 0


def _finding(stem: str, record, node: PinpointResolutionNode, text: str) -> str:
    filing = (
        text[node.attribution_span.start : node.attribution_span.end]
        if node.attribution_span
        else (node.attribution or "")
    )
    lines = [
        f"## {stem[:3]} `{record.source.matched_text}` pin {node.pin_cite} -- {node.outcome.value}"
        + (f" ({node.defect_kind})" if node.defect_kind else ""),
        f"authority {node.authority_id}, cluster {node.cluster_id}, page {', '.join(node.labels)}",
        "",
        f"**filing** (chars {node.attribution_span.start}-{node.attribution_span.end}): {filing}"
        if node.attribution_span
        else f"**filing**: {filing}",
        "",
        f"**page**: {node.passage or '(nothing on the subject)'}",
        "",
        f"_{node.outcome_message}_",
    ]
    return "\n".join(lines)


def score(per_document: dict[str, dict[str, object]]) -> str:
    """Join every WRONG_PINCITE entry to the run's outcomes on the same authority."""
    annotations = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    rows = []
    tally: Counter[str] = Counter()
    for entry in annotations["entries"]:
        if entry["label"] != "WRONG_PINCITE":
            continue
        doc = entry["document"][:-4] + ".json"
        outcomes = per_document.get(doc)
        if outcomes is None:
            continue
        authority = entry.get("authority")
        if authority is None:
            tally["no authority"] += 1
            rows.append(f"  {entry['document'][:3]} {entry['cited_authority'][:40]:40} no authority span")
            continue
        start = authority["span"]["start"]
        root = next((cid for cid, o in outcomes.items() if o["locator_start"] == start), None)
        if root is None:
            tally["no citation at span"] += 1
            rows.append(
                f"  {entry['document'][:3]} {entry['cited_authority'][:40]:40} no extracted citation at {start}"
            )
            continue
        root_authority = outcomes[root]["authority_id"] or root
        members = [o for o in outcomes.values() if (o["authority_id"] or "") == root_authority]
        verdicts = [f"{o['pin'] or '-'}:{o['outcome']}" for o in members]
        caught = any(o["false"] for o in members)
        kinds = sorted({o["kind"] for o in members if o.get("kind")})
        located = any(
            o["outcome"]
            in (
                "quote_on_page",
                "passage_on_page",
                "passage_adjacent",
                "quote_in_opinion",
                "passage_in_opinion",
            )
            for o in members
        )
        if caught:
            tally["called false"] += 1
            for kind in kinds:
                tally[f"  as {kind}"] += 1
        elif located:
            tally["passage or quote located (not called)"] += 1
        elif any(o["outcome"] == "undetermined" for o in members):
            tally["undetermined"] += 1
        elif any(o["outcome"] == "not_testable" for o in members):
            tally["not testable"] += 1
        else:
            tally["not retrieved"] += 1
        flag = "FALSE" if caught else "     "
        rows.append(
            f"  {entry['document'][:3]} {entry['cited_authority'][:40]:40} {flag} {'; '.join(verdicts)}"
        )
    order = [
        "called false",
        "  as quote_not_at_page",
        "  as misquotation",
        "  as content_not_at_page",
        "  as content_absent",
    ]
    ordered = [(k, tally[k]) for k in order if k in tally] + [
        (k, v) for k, v in tally.most_common() if k not in order
    ]
    return "\n".join(
        ["WRONG_PINCITE entries against the run:", *(f"  {k:40} {v:3}" for k, v in ordered), *rows]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--miss-budget", type=int, default=400)
    parser.add_argument("--only", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    out = args.out or args.run_dir.with_name(args.run_dir.name.replace("-identified", "") + "-pinpointed")
    return run(args.run_dir, out, miss_budget=args.miss_budget, only=args.only, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
