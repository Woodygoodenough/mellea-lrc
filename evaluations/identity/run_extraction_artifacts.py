"""Run the identity stage over an extraction run, and count what it concluded.

The input is what ``scripts/extract_bench.py`` on the extraction branch writes:
a directory with a ``manifest.json`` and one extracted-document artifact per
filing. Each is loaded as a real ``ExtractedDocument`` -- spans, citation
objects, authority and co-location ids -- and identified. The output is one
identified-document artifact per filing beside a summary of outcomes.

Two budgets keep the run from spending what it should not. The CourtListener
proxy reports whether a response came from its cache, and the run stops once
uncached responses exceed ``--miss-budget``, because those spend the request
allowance. Model calls are counted from the trace and reported; a run that
wants none passes ``--no-model``, which turns every rule disagreement into an
unresolved root rather than a judgement.

    uv run python -m evaluations.identity.run_extraction_artifacts data/extraction-v2.0
    uv run python -m evaluations.identity.run_extraction_artifacts data/extraction-v2.0 --miss-budget 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from mellea_lrc.courtlistener import CourtListenerClient
from mellea_lrc.serialization import deserialize_extracted_document, serialize_identified_document
from mellea_lrc.validation.identity import identify_document
from mellea_lrc.validation.types import (
    AuthorityMergeNode,
    AuthorityMergeOutcome,
    IdentityResolutionNode,
    MelleaIdentityJudgmentNode,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from mellea_lrc.courtlistener import (
        CourtListenerCitationLookup,
        CourtListenerDocket,
        CourtListenerOpinion,
        CourtListenerSearchResult,
    )
    from mellea_lrc.validation.identity import IdentifiedDocument


class MissBudgetExhausted(RuntimeError):
    """Raised when uncached responses exceed what the run may spend."""


@dataclass
class BudgetedClient:
    """A client that counts responses not served from cache, and stops at a limit."""

    inner: CourtListenerClient
    miss_budget: int
    requests: int = 0
    misses: int = 0

    def _after(self) -> None:
        self.requests += 1
        if self.inner.last_response_cached is not True:
            self.misses += 1
            if self.misses > self.miss_budget:
                msg = f"{self.misses} uncached responses exceed the budget of {self.miss_budget}"
                raise MissBudgetExhausted(msg)

    def lookup_citation(self, volume: str, reporter: str, page: str) -> CourtListenerCitationLookup:
        try:
            return self.inner.lookup_citation(volume, reporter, page)
        finally:
            self._after()

    def get_docket(self, docket_id: str) -> CourtListenerDocket:
        try:
            return self.inner.get_docket(docket_id)
        finally:
            self._after()

    def search(
        self,
        query: str,
        search_type: Literal["r", "rd", "d", "o"],
        cursor: str | None = None,
        *,
        semantic: bool = False,
    ) -> CourtListenerSearchResult:
        try:
            return self.inner.search(query, search_type, cursor, semantic=semantic)
        finally:
            self._after()

    def get_opinion(self, opinion_id: str) -> CourtListenerOpinion:
        try:
            return self.inner.get_opinion(opinion_id)
        finally:
            self._after()


@dataclass
class Tally:
    """What the run concluded, across every document it finished."""

    documents: int = 0
    citations: int = 0
    roots: int = 0
    outcomes: Counter[tuple[str, str | None]] = field(default_factory=Counter)
    decided_by_rule: int = 0
    model_calls: int = 0
    model_failures: int = 0
    corrections: Counter[str] = field(default_factory=Counter)
    merges: int = 0
    disagreements: Counter[str] = field(default_factory=Counter)

    def add(self, identified: IdentifiedDocument) -> None:
        self.documents += 1
        self.citations += len(identified.records)
        for record in identified.records:
            for node in record.trace.nodes:
                if isinstance(node, IdentityResolutionNode):
                    self.roots += 1
                    self.outcomes[(node.outcome.value, node.reason.value if node.reason else None)] += 1
                    self.decided_by_rule += node.decided_by == "rule"
                    for disagreement in node.fields:
                        self.disagreements[disagreement.field] += 1
                elif isinstance(node, MelleaIdentityJudgmentNode):
                    self.model_calls += 1
                    self.model_failures += node.status is ValidationNodeStatus.FAILED
                elif isinstance(node, AuthorityMergeNode):
                    self.merges += node.outcome is AuthorityMergeOutcome.MERGED_INTO
            for correction in record.corrections:
                self.corrections[correction.field] += 1

    def report(self, client: BudgetedClient) -> str:
        lines = [
            f"{self.documents} documents, {self.citations} citations, {self.roots} roots identified",
            f"{client.requests} requests, {client.misses} not served from cache",
            f"{self.decided_by_rule} roots decided by rule, {self.model_calls} model calls "
            f"({self.model_failures} failed)",
            f"{self.merges} parallel citations merged into one authority",
            "outcomes:",
            *(
                f"  {outcome:22} {reason or '':28} {count:4}"
                for (outcome, reason), count in sorted(
                    self.outcomes.items(), key=lambda item: (item[0][0], -item[1])
                )
            ),
        ]
        if self.disagreements:
            lines += ["fields the filing states that disagree with the record:"]
            lines += [f"  {name:26} {count:4}" for name, count in self.disagreements.most_common()]
        if self.corrections:
            lines += ["corrections to the filing's reading:"]
            lines += [f"  {name:26} {count:4}" for name, count in self.corrections.most_common()]
        return "\n".join(lines)


def run(run_dir: Path, out_dir: Path, *, miss_budget: int, limit: int | None, only: str | None) -> int:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = [entry for entry in manifest["entries"] if not only or only in entry["document"]][:limit]
    client = BudgetedClient(CourtListenerClient(), miss_budget=miss_budget)
    tally = Tally()
    (out_dir / "documents").mkdir(parents=True, exist_ok=True)
    stopped: str | None = None
    for entry in entries:
        artifact = run_dir / entry["artifact"]
        document = deserialize_extracted_document(json.loads(artifact.read_text(encoding="utf-8")))
        roots = sum(1 for item in document.citations if item.authority_id == item.citation_id)
        print(
            f"{entry['document'][:60]:60} {len(document.citations):4} citations {roots:4} roots",
            file=sys.stderr,
        )
        try:
            identified = asyncio.run(identify_document(document, client=client))
        except MissBudgetExhausted as exc:
            stopped = str(exc)
            break
        tally.add(identified)
        target = out_dir / "documents" / artifact.name
        target.write_text(
            json.dumps(serialize_identified_document(identified), indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    report = tally.report(client)
    if stopped:
        report += f"\n\nstopped early: {stopped}"
    (out_dir / "summary.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    return 1 if stopped else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path, help="an extraction run directory holding manifest.json")
    parser.add_argument("--out", type=Path, default=None, help="where to write; default <run_dir>-identified")
    parser.add_argument("--miss-budget", type=int, default=25, help="stop after this many uncached responses")
    parser.add_argument("--limit", type=int, default=None, help="only the first N documents")
    parser.add_argument("--only", default=None, help="only documents whose name contains this")
    args = parser.parse_args(argv)
    out = args.out or args.run_dir.with_name(args.run_dir.name + "-identified")
    return run(args.run_dir, out, miss_budget=args.miss_budget, limit=args.limit, only=args.only)


if __name__ == "__main__":
    raise SystemExit(main())
