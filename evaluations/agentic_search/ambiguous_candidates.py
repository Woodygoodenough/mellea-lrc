"""What separates the candidates at an ambiguous locator, and what is left over.

An exact locator lookup that returns several records for one volume, reporter
and page leaves the pipeline to decide which record the filing meant. Three
things decide it before any search runs, and each is free:

1. **Merging duplicates.** Most multi-record answers are one decision the
   archive holds more than once. `validation/duplicate_clusters.py` merges them.
2. **The case name the filing wrote.** `validation/candidate_selection.py`
   consults it when the merged count still exceeds the limit.
3. **The court and year the filing states.** `search/narrowing.py` compares
   them against each record.

This script measures how far those three get on a real corpus, and reports what
is left for the search loop to do. It answers the questions section 7 of
`exploration/notes/agentic-search-population.md` lists as unmeasured.

Every lookup goes through the caching proxy, and the client reports whether a
response was served from cache. A cached response spends no request allowance,
so the run stops as soon as uncached responses exceed ``--miss-budget`` rather
than spending an allowance it does not own. The default is deliberately small.

Run it as::

    uv run python -m evaluations.agentic_search.ambiguous_candidates <corpus.jsonl>

The corpus is one JSON object per line with ``filename``, ``text`` and
``list_hallucination_types``, which is the shape of the LePhantomCite splits.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.courtlistener import CourtListenerClient, CourtListenerError
from mellea_lrc.extraction import extract_from_plain_text
from mellea_lrc.search import CandidateFacts, CitationFacts, narrow
from mellea_lrc.validation.candidate_selection import CANDIDATE_SELECTION_LIMIT
from mellea_lrc.validation.duplicate_clusters import matching_case_names, merge_duplicates

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from mellea_lrc.courtlistener.opinion_models import CourtListenerOpinionCluster

DEFAULT_MISS_BUDGET = 20
UNLABELLED = "sound"


@dataclass(frozen=True, slots=True)
class Locator:
    """One citation reduced to what the lookup endpoint takes, plus its parties."""

    volume: str
    reporter: str
    page: str
    plaintiff: str | None
    defendant: str | None
    court_id: str | None
    year: str | None
    label: str

    @property
    def key(self) -> tuple[str, str, str]:
        """The lookup's own identity, so one locator is fetched once."""
        return (self.volume, self.reporter, self.page)

    def __str__(self) -> str:
        """The citation as a reader would write it."""
        return f"{self.volume} {self.reporter} {self.page}"


@dataclass
class Tally:
    """Counts accumulated over every ambiguous locator seen."""

    looked_up: int = 0
    not_found: int = 0
    one_record: int = 0
    ambiguous: int = 0
    merged_to_one: int = 0
    merged_within_limit: int = 0
    over_limit_after_merging: int = 0
    name_narrowed: int = 0
    unresolved_after_name: int = 0
    narrowing_separated: int = 0
    still_unseparated: int = 0
    records_with_court: int = 0
    records_with_date: int = 0
    records_total: int = 0
    labels_over_limit: Counter[str] = field(default_factory=Counter)
    labels_still_unseparated: Counter[str] = field(default_factory=Counter)
    unseparated: list[str] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)


def locators(path: Path) -> Iterator[Locator]:
    """Extract every full case citation in the corpus, with its defect label."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        labels = record.get("list_hallucination_types") or {}
        document = extract_from_plain_text(record["text"], source_path=record["filename"])
        for item in document.citations:
            citation = item.citation
            if not isinstance(citation, FullCaseCitation):
                continue
            if not (citation.volume and citation.reporter and citation.page):
                continue
            written = record["text"][item.locator_span.start : item.locator_span.end]
            yield Locator(
                volume=citation.volume,
                reporter=citation.reporter.canonical,
                page=citation.page,
                plaintiff=citation.plaintiff,
                defendant=citation.defendant,
                court_id=citation.court,
                year=citation.date.year if citation.date else None,
                label=str(labels.get(written, UNLABELLED)),
            )


def _facts(clusters: Sequence[CourtListenerOpinionCluster]) -> list[CandidateFacts]:
    """Project archive records into what narrowing compares."""
    return [
        CandidateFacts(
            identifier=cluster.cluster_id or f"record-{index}",
            case_name=cluster.case_name,
            court_id=cluster.court_id,
            year=cluster.year,
        )
        for index, cluster in enumerate(clusters)
    ]


def measure(path: Path, *, miss_budget: int, limit: int) -> tuple[Tally, int, int]:
    """Look every locator up once and tally what separates the ambiguous ones."""
    client = CourtListenerClient()
    tally = Tally()
    seen: set[tuple[str, str, str]] = set()
    requests_made = 0
    misses = 0
    for locator in locators(path):
        if locator.key in seen:
            continue
        seen.add(locator.key)
        try:
            lookup = client.lookup_citation(locator.volume, locator.reporter, locator.page)
        except CourtListenerError as exc:
            sys.stderr.write(f"  {locator}: {exc.message}\n")
            if exc.failure_type == "api_limit":
                sys.stderr.write("  stopping: the allowance is gone\n")
                break
            continue
        requests_made += 1
        if client.last_response_cached is not True:
            misses += 1
            if misses > miss_budget:
                sys.stderr.write(f"  stopping after {misses} uncached responses, which spend the allowance\n")
                break
        _record(tally, locator, lookup.clusters, limit=limit)
    return tally, requests_made, misses


def _record(
    tally: Tally,
    locator: Locator,
    clusters: Sequence[CourtListenerOpinionCluster],
    *,
    limit: int,
) -> None:
    """Tally one lookup answer, ignoring everything that is not ambiguous."""
    tally.looked_up += 1
    if not clusters:
        tally.not_found += 1
        return
    if len(clusters) == 1:
        tally.one_record += 1
        return
    tally.ambiguous += 1
    tally.records_total += len(clusters)
    tally.records_with_court += sum(1 for cluster in clusters if cluster.court_id)
    tally.records_with_date += sum(1 for cluster in clusters if cluster.date_filed)

    distinct = len(merge_duplicates(clusters))
    if distinct == 1:
        tally.merged_to_one += 1
    if distinct <= limit:
        tally.merged_within_limit += 1
        return

    tally.over_limit_after_merging += 1
    tally.labels_over_limit[locator.label] += 1
    matches = matching_case_names(clusters, plaintiff=locator.plaintiff, defendant=locator.defendant)
    if matches and len(matches) <= limit:
        tally.name_narrowed += 1
        return

    tally.unresolved_after_name += 1
    narrowing = narrow(
        CitationFacts(
            plaintiff=locator.plaintiff,
            defendant=locator.defendant,
            court_id=locator.court_id,
            year=locator.year,
        ),
        _facts(clusters),
        limit=limit,
    )
    if narrowing.separated:
        tally.narrowing_separated += 1
        return
    tally.still_unseparated += 1
    tally.labels_still_unseparated[locator.label] += 1
    tally.unseparated.append(f"{locator} ({len(clusters)} records, {distinct} distinct, {locator.label})")
    tally.explanations.append(_explain(locator, clusters))


def _explain(locator: Locator, clusters: Sequence[CourtListenerOpinionCluster]) -> str:
    """What the filing wrote against what the archive puts on the page.

    A page carrying many unrelated cases is a table of decisions, where a
    reporter prints unpublished dispositions. Showing the names the archive
    holds beside the name the filing wrote distinguishes a filing naming a case
    the page does not carry from a filing whose parties were never recovered.

    The alphabetical range is reported because a contiguous slice of an
    alphabetical table would bound the page, and a name sorting outside those
    bounds could not be on it. Measured, the ranges are not contiguous slices:
    `788 F.2d 9` runs from `Acker` to `United States v. Martinez` in 27 records,
    so the bound establishes nothing and the range is shown as a description
    rather than as a test.
    """
    named = sorted(cluster.case_name for cluster in clusters if cluster.case_name)
    written = " v. ".join(part for part in (locator.plaintiff, locator.defendant) if part)
    if not written:
        return f"      {locator}: the filing recovered no parties; {len(named)} named records on the page"
    if not named:
        return f"      {locator}: the filing writes {written!r}; no record on the page is named"
    span = f"{named[0]!r} .. {named[-1]!r}"
    inside = named[0].casefold() <= written.casefold() <= named[-1].casefold()
    place = "inside" if inside else "outside"
    return (
        f"      {locator}: the filing writes {written!r}; {len(named)} named records "
        f"running {span}, which the written name sorts {place}"
    )


def report(tally: Tally, requests_made: int, misses: int, *, limit: int) -> str:
    """Render the whole measurement as text."""
    lines = [
        f"{requests_made} locators looked up, {misses} of them not served from cache.",
        "",
        "1. What the exact locator lookup returned",
        "-" * 52,
        f"{tally.one_record:5d}  one record, so nothing has to choose",
        f"{tally.not_found:5d}  no record, which is the search route's population",
        f"{tally.ambiguous:5d}  more than one record, which is this loop's population",
        "",
        f"2. Separating the {tally.ambiguous} that returned more than one record",
        "-" * 52,
        f"{tally.merged_to_one:5d}  are one decision the archive holds more than once",
        f"{tally.merged_within_limit:5d}  are within the limit of {limit} once duplicates are merged",
        f"{tally.over_limit_after_merging:5d}  still exceed it",
        "",
        f"3. What separates the {tally.over_limit_after_merging} that exceed the limit",
        "-" * 52,
        f"{tally.name_narrowed:5d}  the case name the filing wrote picks out {limit} or fewer",
        f"{tally.unresolved_after_name:5d}  the case name does not",
        f"{tally.narrowing_separated:5d}    of which the court or year the filing states separates",
        f"{tally.still_unseparated:5d}    of which nothing free separates, so a query is needed",
        "",
        "4. What the archive's records carry",
        "-" * 52,
        f"{tally.records_with_court:5d} of {tally.records_total} records state a court",
        f"{tally.records_with_date:5d} of {tally.records_total} records state a decision date",
    ]
    if tally.labels_over_limit:
        lines += ["", "5. Label of the locators that exceed the limit after merging", "-" * 52]
        lines += [f"{count:5d}  {label}" for label, count in tally.labels_over_limit.most_common()]
    if tally.unseparated:
        lines += ["", "6. The locators nothing free separates", "-" * 52]
        lines += [f"      {entry}" for entry in tally.unseparated]
        lines += ["", "7. What each of them wrote, against what the page holds", "-" * 52]
        lines += tally.explanations
    return "\n".join(lines)


def main(argv: Sequence[str]) -> int:
    """Measure one corpus named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="one JSON object per line")
    parser.add_argument(
        "--miss-budget",
        type=int,
        default=DEFAULT_MISS_BUDGET,
        help="stop after this many responses that were not served from cache",
    )
    parser.add_argument("--limit", type=int, default=CANDIDATE_SELECTION_LIMIT)
    args = parser.parse_args(argv[1:])
    if not args.corpus.is_file():
        sys.stderr.write(f"no such corpus: {args.corpus}\n")
        return 2
    tally, requests_made, misses = measure(
        args.corpus,
        miss_budget=args.miss_budget,
        limit=args.limit,
    )
    print(report(tally, requests_made, misses, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
