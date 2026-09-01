"""Count which citations a search stage could act on, and what they are labelled.

The brief in ``exploration/notes/agentic-search-handoff.md`` proposes making the
search stage a loop, on the reasoning that a citation whose single query returns
nothing currently ends unresolved. That reasoning is about the ``unresolved``
bucket, so the first question is how large that bucket is and what is in it.

This script answers that from a locator probe's own output. It sends no
requests and calls no model: it reads the probe's JSON, parses each citation
string with eyecite, and counts. Everything it reports is therefore free to
re-run and does not depend on the API allowance.

Run it as::

    uv run python -m evaluations.agentic_search.search_population <probe.json>

The probe file is produced by ``evaluations/lephantomcite/locator_probe.py`` on
``experiment/general-explorations``. It is a run artifact rather than a tracked
file, and it records one row per case citation with the outcome of an exact
locator lookup and the benchmark's own defect label.

Two limits on what these counts can show, both of which matter for how they are
read:

* The probe stores each citation's **locator span**, not the citation as
  written. A court parenthetical survives only when eyecite's span happened to
  include it, so any count of how many citations carry a court is a lower bound
  and is reported here as such rather than as the gate's true pass rate.
* The corpus is defect-injected. A label distribution over it describes how the
  benchmark was generated as much as it describes real filings. Section 7.1 of
  ``exploration/notes/caselaw-archive.md`` works through one case where that
  distinction changed the reading of a result.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eyecite import get_citations
from eyecite.models import FullCaseCitation

from mellea_lrc.validation.candidate_selection import CANDIDATE_SELECTION_LIMIT

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

# Reporter abbreviations that identify a record in a paid database rather than
# naming a printed reporter. Section 11 of `exploration/notes/open-ended-search.md`
# establishes that CourtListener's search endpoint returns nothing for these
# even where its citation-lookup endpoint holds the cluster, so a name search
# cannot recover one.
VENDOR_REPORTERS = ("WL", "LEXIS")

# Abbreviations that `reporters-db` maps to a case reporter but which name a
# statute, a regulation or an agency document in the corpora. Section 5 of
# `open-ended-search.md` identifies each one. They are counted apart because a
# search stage has nothing to look for.
NON_CASE_REPORTERS = ("FERC", "O.S.", "OK", "CMR", "Op. O.L.C.", "Fed. Reg.")


@dataclass(frozen=True, slots=True)
class ParsedRow:
    """One probe record with whatever eyecite could recover from its locator."""

    cited_text: str
    label: str
    outcome: str
    cluster_count: int
    reporter: str | None
    court: str | None
    year: int | None

    @property
    def is_vendor(self) -> bool:
        """Whether the locator names a Westlaw or LEXIS record."""
        return self.reporter is not None and any(v in self.reporter.upper() for v in VENDOR_REPORTERS)

    @property
    def is_non_case(self) -> bool:
        """Whether the locator names something that is not a case reporter."""
        return self.reporter is not None and self.reporter in NON_CASE_REPORTERS


def parse_rows(records: Iterable[Mapping[str, Any]]) -> list[ParsedRow]:
    """Parse every probe record's locator span, keeping the ones eyecite reads."""
    rows: list[ParsedRow] = []
    for record in records:
        cited_text = str(record["cited_text"])
        citations = [c for c in get_citations(cited_text) if isinstance(c, FullCaseCitation)]
        citation = citations[0] if citations else None
        rows.append(
            ParsedRow(
                cited_text=cited_text,
                label=str(record["label"]),
                outcome=str(record["outcome"]),
                cluster_count=int(record["cluster_count"]),
                reporter=citation.groups.get("reporter") if citation else None,
                court=citation.metadata.court if citation else None,
                year=citation.year if citation else None,
            )
        )
    return rows


def _table(title: str, counts: Counter[str], total: int) -> str:
    """Render one count table with a share of ``total``."""
    lines = [title, "-" * len(title)]
    for key, value in counts.most_common():
        share = f"{100 * value / total:5.1f}%" if total else "    - "
        lines.append(f"{value:5d}  {share}  {key}")
    return "\n".join(lines)


def report(rows: Sequence[ParsedRow]) -> str:
    """Build the whole report as text."""
    sections: list[str] = []
    outcomes = Counter(row.outcome for row in rows)
    sections.append(_table(f"1. Locator outcome over {len(rows)} case citations", outcomes, len(rows)))

    unresolved = [row for row in rows if row.outcome == "unresolved"]
    sections.append(
        _table(
            f"2. Label of the {len(unresolved)} unresolved locators",
            Counter(row.label for row in unresolved),
            len(unresolved),
        )
    )

    kinds: Counter[str] = Counter()
    for row in unresolved:
        if row.reporter is None:
            kinds["eyecite reads no full case citation"] += 1
        elif row.is_vendor:
            kinds["a Westlaw or LEXIS record, which search cannot reach"] += 1
        elif row.is_non_case:
            kinds["a statute, regulation or agency document, not a case"] += 1
        else:
            kinds["a printed reporter a name search could reach"] += 1
    sections.append(_table("3. What the unresolved locators are", kinds, len(unresolved)))

    ambiguous = [row for row in rows if row.outcome == "ambiguous"]
    sections.append(
        _table(
            f"4. Label of the {len(ambiguous)} ambiguous locators",
            Counter(row.label for row in ambiguous),
            len(ambiguous),
        )
    )
    sections.append(
        _table(
            "5. How many clusters an ambiguous locator has",
            Counter(f"{row.cluster_count} clusters" for row in ambiguous),
            len(ambiguous),
        )
    )

    deferred = [row for row in ambiguous if row.cluster_count > CANDIDATE_SELECTION_LIMIT]
    sections.append(
        f"6. The {len(deferred)} ambiguous locators the selection guard drops whole\n"
        "-------------------------------------------------------------------\n"
        f"`validation/candidate_selection.py` sets CANDIDATE_SELECTION_LIMIT to\n"
        f"{CANDIDATE_SELECTION_LIMIT}. A locator with more clusters than that is deferred with zero\n"
        "candidates evaluated, so nothing is checked against it at all.\n"
        + _table(
            f"   label of those {len(deferred)}",
            Counter(row.label for row in deferred),
            len(deferred),
        )
    )

    by_label: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_label[row.label][row.outcome] += 1
    lines = ["7. Every defect label against its locator outcome", "-" * 48]
    for label in sorted(by_label):
        total = sum(by_label[label].values())
        spread = ", ".join(f"{outcome} {count}" for outcome, count in by_label[label].most_common())
        lines.append(f"{total:5d}  {label}: {spread}")
    sections.append("\n".join(lines))

    with_court = sum(1 for row in unresolved if row.court is not None)
    sections.append(
        "8. Court identifiers in the unresolved bucket\n"
        "---------------------------------------------\n"
        f"{with_court} of {len(unresolved)} unresolved locators carry a court eyecite can read.\n"
        "This is a lower bound and not the gate's pass rate: the probe stores the\n"
        "locator span, so a court parenthetical is present only where eyecite's\n"
        "span reached it. Measuring the gate properly needs the excerpt text."
    )
    return "\n\n".join(sections)


def main(argv: Sequence[str]) -> int:
    """Read a probe file named on the command line and print the report."""
    if len(argv) != 2:
        sys.stderr.write(f"usage: {argv[0]} <locator-probe.json>\n")
        return 2
    path = Path(argv[1])
    if not path.is_file():
        sys.stderr.write(f"no such probe file: {path}\n")
        return 2
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(report(parse_rows(payload["records"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
