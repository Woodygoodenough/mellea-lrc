"""Separating candidates at one locator using only what the filing already states.

This is the search loop's first move, and it sends no request. When a lookup
returns several records for one volume, reporter and page, the records are
already in hand, so comparing them against the court, year and party names the
filing itself wrote costs nothing. Only when that fails to separate them does
anything have to be asked of CourtListener.

It runs after the two free moves the pipeline already makes.
`validation/duplicate_clusters.py` merges the records that are one decision the
archive holds more than once, and `validation/candidate_selection.py` then picks
out the records carrying the case name the filing wrote. Narrowing is for what
is left: a page where the name matched nothing, or matched too many.

**Measured, this separates nothing on the ambiguous-locator route, and it is
not wired into that route for exactly that reason.** Over 659 locators, merging
and the case name leave nine ambiguous locators, and this module separates none
of them. Two reasons, both structural. A record from the citation-lookup
endpoint carries **no court** -- the payload has no court field, which is why
`validation/court_retrieval` fetches the docket to get one, a request per
candidate -- so the court comparison cannot fire there. And each of the nine is
a table of decisions from one court in one year, so the year separates nothing
either. Section 4 of `exploration/notes/agentic-search-population.md` has the
measurement.

A search result does carry `court_id` and `dateFiled`, so all three comparisons
are available on a search route, where a query returning 111 results is
currently deferred whole. **Whether they separate anything there is unmeasured**,
because a search is not cacheable and the measurement costs request allowance.
That is what this module is waiting on, and if the answer is that it separates
nothing there either, it should be deleted rather than kept.

Three rules keep this from becoming a way to hide findings.

**Nothing is excluded on an absence.** A filing that states no court has its
court compared against nothing, and every candidate survives that comparison. An
absent field is not evidence, which is the same rule the rest of the project
applies to a missing record.

**A case-name disagreement never excludes.** `case_name_mismatch` is the defect
this stage exists to find, so a candidate whose name disagrees with the filing
is exactly the candidate worth looking at. A name that agrees promotes a
candidate; a name that disagrees only ranks it last.

**Narrowing never returns an empty set.** If every candidate is contradicted,
the contradiction is more likely to be in the filing than in all of them at
once, so the exclusions are reported and none is applied. A caller that received
an empty set would conclude the locator matched nothing, which is a different
and wrong finding.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from mellea_lrc.validation.duplicate_clusters import name_covers, name_words

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "YEAR_TOLERANCE",
    "CandidateFacts",
    "CitationFacts",
    "NarrowedCandidate",
    "Narrowing",
    "NarrowingOutcome",
    "narrow",
]

# A citation's parenthetical states the year the case was decided and
# CourtListener's `dateFiled` states when the opinion was filed. The two agree
# for almost every case and are one apart for a decision issued at the end of a
# year, for a reporter volume dated the following year, and for an opinion
# amended after it was first filed. One year is therefore not a disagreement,
# and two or more is: `run_year_check` still reports the exact comparison, and
# this tolerance governs only whether a candidate is dropped from consideration.
# The search query built in `case_search` uses the same window for the same
# reason.
YEAR_TOLERANCE = 1

# A case name must reduce to at least this many distinctive words before it can
# be compared. `validation/duplicate_clusters.py` sets the same floor, and for
# the same reason: one word matches any record sharing one party.
MINIMUM_NAME_WORDS = 2


class NarrowingOutcome(str, Enum):
    """What comparing one candidate against the filing's own evidence concluded."""

    KEPT = "kept"
    """Nothing the filing states rules this candidate out."""

    EXCLUDED_BY_COURT = "excluded_by_court"
    """The filing names a court and this candidate is from a different one."""

    EXCLUDED_BY_YEAR = "excluded_by_year"
    """The filing states a year more than ``YEAR_TOLERANCE`` from this one."""


@dataclass(frozen=True, slots=True)
class CitationFacts:
    """What the filing itself says about the case it is citing.

    The parties are held apart rather than as one name because that is how the
    citation carries them and how the name comparison consumes them.
    """

    plaintiff: str | None = None
    defendant: str | None = None
    court_id: str | None = None
    year: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateFacts:
    """What one retrieved candidate says about itself."""

    identifier: str
    case_name: str | None = None
    court_id: str | None = None
    year: str | None = None


@dataclass(frozen=True, slots=True)
class NarrowedCandidate:
    """One candidate with the comparison that decided its place."""

    citation: CitationFacts
    candidate: CandidateFacts
    outcome: NarrowingOutcome
    name_agrees: bool | None
    """``None`` where the filing named too little to compare, or the record is unnamed."""
    court_agrees: bool | None
    """``None`` where either side states no court, so nothing was compared."""
    year_distance: int | None
    """Whole years between the two, or ``None`` where either side states none."""

    @property
    def reason(self) -> str:
        """One sentence a reader can check the decision against."""
        if self.outcome is NarrowingOutcome.EXCLUDED_BY_COURT:
            return (
                f"The filing names court {_show(self.citation.court_id)} and this "
                f"candidate is from {_show(self.candidate.court_id)}."
            )
        if self.outcome is NarrowingOutcome.EXCLUDED_BY_YEAR:
            return (
                f"The filing states {_show(self.citation.year)} and this candidate is "
                f"{_show(self.candidate.year)}, {self.year_distance} years apart and "
                f"beyond the tolerance of {YEAR_TOLERANCE}."
            )
        return "Kept: " + ", ".join(
            (
                _phrase(self.name_agrees, "the case name", "no case name could be compared"),
                _phrase(self.court_agrees, "the court", "no court could be compared"),
                self._year_phrase(),
            )
        )

    def _year_phrase(self) -> str:
        if self.year_distance is None:
            return "no year could be compared"
        if self.year_distance == 0:
            return "the year agrees"
        return f"the year is {self.year_distance} away"


@dataclass(frozen=True, slots=True)
class Narrowing:
    """Every candidate at one locator, ranked, with what survived and why."""

    considered: tuple[NarrowedCandidate, ...]
    """Every candidate, ranked best first, including the excluded ones."""

    kept: tuple[NarrowedCandidate, ...]
    """The candidates nothing the filing states rules out, ranked best first."""

    limit: int
    """The number of candidates the caller is willing to evaluate."""

    exclusions_withheld: bool
    """Whether every candidate was contradicted, so no exclusion was applied."""

    @property
    def separated(self) -> bool:
        """Whether narrowing alone brought the candidates within the limit."""
        return len(self.kept) <= self.limit

    @property
    def selected(self) -> tuple[NarrowedCandidate, ...]:
        """The candidates to evaluate, empty when narrowing did not separate them."""
        return self.kept if self.separated else ()

    @property
    def summary(self) -> str:
        """One sentence naming what narrowing achieved."""
        if self.exclusions_withheld:
            return (
                f"Every one of {len(self.considered)} candidates is contradicted by the "
                "filing's own evidence, so none was excluded."
            )
        if self.separated:
            return (
                f"Narrowed {len(self.considered)} candidates to {len(self.kept)} using the "
                f"filing's own evidence, within the limit of {self.limit}."
            )
        return (
            f"Narrowed {len(self.considered)} candidates to {len(self.kept)} using the "
            f"filing's own evidence, still above the limit of {self.limit}."
        )


def narrow(
    citation: CitationFacts,
    candidates: Sequence[CandidateFacts],
    *,
    limit: int,
) -> Narrowing:
    """Rank candidates against the filing's own evidence and drop the contradicted."""
    if limit < 1:
        msg = "Narrowing requires a limit of at least one candidate"
        raise ValueError(msg)
    written = name_words(citation.plaintiff) | name_words(citation.defendant)
    compared = [_compare(citation, candidate, written) for candidate in candidates]
    kept = [item for item in compared if item.outcome is NarrowingOutcome.KEPT]
    withheld = bool(compared) and not kept
    if withheld:
        # Every candidate contradicted means the filing disagrees with the whole
        # page, which is a finding about the filing rather than about any one
        # candidate. Reporting no candidates would read as a locator miss.
        compared = [_kept(item) for item in compared]
    ranked = tuple(sorted(compared, key=_rank))
    return Narrowing(
        considered=ranked,
        kept=tuple(item for item in ranked if item.outcome is NarrowingOutcome.KEPT),
        limit=limit,
        exclusions_withheld=withheld,
    )


def _compare(
    citation: CitationFacts,
    candidate: CandidateFacts,
    written: set[str],
) -> NarrowedCandidate:
    """Compare one candidate against the filing without excluding on an absence."""
    court_agrees = _court_agrees(citation.court_id, candidate.court_id)
    year_distance = _year_distance(citation.year, candidate.year)
    if court_agrees is False:
        outcome = NarrowingOutcome.EXCLUDED_BY_COURT
    elif year_distance is not None and year_distance > YEAR_TOLERANCE:
        outcome = NarrowingOutcome.EXCLUDED_BY_YEAR
    else:
        outcome = NarrowingOutcome.KEPT
    return NarrowedCandidate(
        citation=citation,
        candidate=candidate,
        outcome=outcome,
        name_agrees=_name_agrees(written, candidate.case_name),
        court_agrees=court_agrees,
        year_distance=year_distance,
    )


def _kept(item: NarrowedCandidate) -> NarrowedCandidate:
    """Restore one excluded candidate when every candidate was excluded."""
    if item.outcome is NarrowingOutcome.KEPT:
        return item
    return NarrowedCandidate(
        citation=item.citation,
        candidate=item.candidate,
        outcome=NarrowingOutcome.KEPT,
        name_agrees=item.name_agrees,
        court_agrees=item.court_agrees,
        year_distance=item.year_distance,
    )


def _rank(item: NarrowedCandidate) -> tuple[int, int, int, int, str]:
    """Order candidates best first: kept, then name, court and year agreement.

    A comparison that could not be made ranks between agreement and
    disagreement. A record the filing's words are absent from is the least
    likely to be the case the filing meant, and a record with nothing to
    compare is merely unknown.
    """
    return (
        0 if item.outcome is NarrowingOutcome.KEPT else 1,
        _order(item.name_agrees),
        _order(item.court_agrees),
        item.year_distance if item.year_distance is not None else YEAR_TOLERANCE + 1,
        item.candidate.identifier,
    )


def _order(agreement: bool | None) -> int:
    """Rank one three-valued comparison: agrees, could not compare, disagrees."""
    return {True: 0, None: 1, False: 2}[agreement]


def _name_agrees(written: set[str], recorded: str | None) -> bool | None:
    """Whether a record carries the party names the filing wrote.

    Uses the same containment rule as `validation/duplicate_clusters.py`, which
    tolerates the abbreviations a citation conventionally uses -- `Reyes v.
    Pac. Bell` against `Victor Reyes v. Pacific Bell`. Comparing the two names
    for equality instead would report a disagreement for almost every correct
    citation.
    """
    if len(written) < MINIMUM_NAME_WORDS or not recorded:
        return None
    return name_covers(name_words(recorded), written)


def _court_agrees(extracted: str | None, retrieved: str | None) -> bool | None:
    """Compare court identifiers, returning None where either side states none."""
    if not extracted or not retrieved:
        return None
    return extracted == retrieved


def _year_distance(extracted: str | None, retrieved: str | None) -> int | None:
    """Whole years between the two, or None where either is missing or unreadable."""
    left = _year(extracted)
    right = _year(retrieved)
    if left is None or right is None:
        return None
    return abs(left - right)


def _year(value: str | None) -> int | None:
    """Read a four-digit year from a citation year or an ISO filing date."""
    if not value:
        return None
    with contextlib.suppress(ValueError):
        return int(value.strip()[:4])
    return None


def _phrase(agreement: bool | None, subject: str, absent: str) -> str:
    """Render one three-valued comparison for a reason sentence."""
    if agreement is None:
        return absent
    return f"{subject} agrees" if agreement else f"{subject} does not agree"


def _show(value: str | None) -> str:
    """Render a possibly absent field for a reason sentence."""
    return value if value else "none"
