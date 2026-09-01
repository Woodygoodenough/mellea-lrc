"""Separating candidates at one locator using only what the filing already states.

This is the search loop's first move, and it sends no request. When an exact
locator lookup returns several clusters for one volume, reporter and page, the
clusters are already in hand, so comparing them against the court, year and case
name the filing itself wrote costs nothing. Only when that fails to separate
them does anything have to be asked of CourtListener.

The move matters because the pipeline currently makes no move at all here.
`validation/candidate_selection.py` caps candidate evaluation at three, and a
locator returning more clusters than that is deferred with zero candidates
selected -- no case-name check, no year check, no court check runs against any
of them. Section 5 of `exploration/notes/agentic-search-population.md` counts 23
citations in 1,334 that reach no verdict for that reason.

Three rules keep this from becoming a way to hide findings.

**Nothing is excluded on an absence.** A filing that states no court has its
court compared against nothing, and every candidate survives that comparison. An
absent field is not evidence, which is the same rule the rest of the project
applies to a missing record.

**A case-name disagreement never excludes.** `case_name_mismatch` is the defect
this stage exists to find, so a candidate whose name disagrees with the filing
is exactly the candidate worth looking at. A name that agrees promotes a
candidate; a name that disagrees does nothing.

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
YEAR_TOLERANCE = 1


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
    """What the filing itself says about the case it is citing."""

    case_name: str | None = None
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
    name_agrees: bool
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
        parts = ["the case name agrees" if self.name_agrees else "the case name does not agree"]
        if self.court_agrees is True:
            parts.append("the court agrees")
        elif self.court_agrees is None:
            parts.append("no court could be compared")
        if self.year_distance == 0:
            parts.append("the year agrees")
        elif self.year_distance is None:
            parts.append("no year could be compared")
        else:
            parts.append(f"the year is {self.year_distance} away")
        return "Kept: " + ", ".join(parts) + "."


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
    compared = [_compare(citation, candidate) for candidate in candidates]
    kept = [item for item in compared if item.outcome is NarrowingOutcome.KEPT]
    withheld = bool(compared) and not kept
    if withheld:
        # Every candidate contradicted means the filing disagrees with the whole
        # page, which is a finding about the filing rather than about any one
        # candidate. Reporting no candidates would read as a locator miss.
        compared = [_kept(item) for item in compared]
        kept = list(compared)
    ranked = tuple(sorted(compared, key=_rank))
    return Narrowing(
        considered=ranked,
        kept=tuple(item for item in ranked if item.outcome is NarrowingOutcome.KEPT),
        limit=limit,
        exclusions_withheld=withheld,
    )


def _compare(citation: CitationFacts, candidate: CandidateFacts) -> NarrowedCandidate:
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
        name_agrees=_names_agree(citation.case_name, candidate.case_name),
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
    """Order candidates best first: kept, then name, court, and year agreement."""
    return (
        0 if item.outcome is NarrowingOutcome.KEPT else 1,
        0 if item.name_agrees else 1,
        {True: 0, None: 1, False: 2}[item.court_agrees],
        item.year_distance if item.year_distance is not None else YEAR_TOLERANCE + 1,
        item.candidate.identifier,
    )


def _names_agree(extracted: str | None, retrieved: str | None) -> bool:
    """Compare case names the way `run_exact_case_name_check` does."""
    if extracted is None or retrieved is None:
        return False
    return _normalize(extracted) == _normalize(retrieved)


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


def _normalize(value: str) -> str:
    """Collapse whitespace and case, as the exact case-name check does."""
    return " ".join(value.split()).casefold()


def _show(value: str | None) -> str:
    """Render a possibly absent field for a reason sentence."""
    return value if value else "none"
