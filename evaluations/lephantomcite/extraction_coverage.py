"""Measure how many LePhantomCite citations this project's extractor recovers.

LePhantomCite has no extraction stage to compare against: its agent reads the
excerpt and writes citations into a natural-language belief state, so a citation
it never noticed and one it noticed and judged wrongly are the same event in its
metric. This measures the stage separately, which is the only way to tell those
apart.

The comparison is symmetric. Each benchmark citation string is run through the
same extractor as the excerpt it came from, and the two are compared on the
identifier that results -- volume, reporter and page, with punctuation, spacing
and case removed. A benchmark that writes `F.Supp.2d` and an excerpt that writes
`F. Supp. 2d` name one authority, and neither spelling is more correct.

Short forms count. `755 N.E.2d at 598` is one of the benchmark's citation
strings, and a system that reports only self-contained citations has not found
it.
"""

from __future__ import annotations

import contextlib
import io
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mellea_lrc.core.citations import FullCaseCitation, ShortCaseCitation
from mellea_lrc.extraction import extract_from_plain_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from evaluations.lephantomcite.dataset import Excerpt

_NON_ALNUM = re.compile(r"[^a-z0-9]")


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Recovered and missed identifiers across a set of excerpts."""

    gold_identifiers: int
    recovered: int
    excerpts: int
    fully_recovered_excerpts: int
    missed: tuple[tuple[str, str], ...]

    @property
    def recall(self) -> float:
        """Share of benchmark identifiers the extractor recovered."""
        return self.recovered / self.gold_identifiers if self.gold_identifiers else 0.0


def identifiers(text: str) -> frozenset[str]:
    """Return every reporter identifier the extractor finds in a run of text.

    eyecite writes overlap diagnostics to stdout on some inputs. They are
    diagnostics rather than failures, and they would otherwise flood a sweep of
    several hundred excerpts, so they are suppressed here rather than silenced
    globally.
    """
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        document = extract_from_plain_text(text)
    found = set()
    for item in document.citations:
        citation = item.citation
        if not isinstance(citation, FullCaseCitation | ShortCaseCitation):
            continue
        volume, reporter, page = citation.volume, citation.reporter, citation.page
        if volume and reporter and page:
            found.add(f"{volume}|{_NON_ALNUM.sub('', reporter.lower())}|{page}")
    return frozenset(found)


def measure(excerpts: Sequence[Excerpt]) -> CoverageReport:
    """Compare extractor output against each excerpt's stated citations."""
    gold_total = recovered = fully = 0
    missed: list[tuple[str, str]] = []

    for excerpt in excerpts:
        ours = identifiers(excerpt.text)
        gold: set[str] = set()
        for citation in excerpt.citations:
            gold |= identifiers(citation.cited_text)
        gold_total += len(gold)
        recovered += len(gold & ours)
        missed.extend((excerpt.excerpt_id, identifier) for identifier in sorted(gold - ours))
        if gold and gold <= ours:
            fully += 1

    return CoverageReport(
        gold_identifiers=gold_total,
        recovered=recovered,
        excerpts=len(excerpts),
        fully_recovered_excerpts=fully,
        missed=tuple(missed),
    )
