"""Whether the case name a filing wrote is the name the archive holds, by rule.

An exact comparison reports a disagreement for most correct citations: a filing
writes `Reyes v. Pac. Bell` for `Victor Reyes v. Pacific Bell`, or `Golden` for
`Bobby Ray Golden`, and those are the ordinary way a case is cited rather than
defects. Sending each of them to a model to be told so costs a call per
citation for an answer a rule can give.

The rule is containment, one side at a time. A case name has up to two sides,
and every distinctive word the filing wrote on a side must appear in the
corresponding side of the record, allowing the abbreviations a citation
conventionally uses. Sides may swap, since a cross-appeal reverses them. What
the filing did not write is not held against it: `Golden` is contained in
`Bobby Ray Golden` because the filing's one word is there.

Two things this deliberately does not do. It does not decide from an absence:
a filing that wrote no name, or a record that carries none, is `UNAVAILABLE`
and not a mismatch. And a disagreement here is not a finding, only the trigger
for a closer look: `MISMATCH` sends the citation to the composite model
judgement, which sees the filing's context rather than the two strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from mellea_lrc.validation.duplicate_clusters import name_covers, name_words, ordered_words
from mellea_lrc.validation.types import CaseNameAgreement

_SIDE_SEPARATOR = re.compile(r"\s+vs?\.?\s+", re.IGNORECASE)
_ACRONYM = re.compile(r"\b[A-Z]{3,}\b")


@dataclass(frozen=True, slots=True)
class CaseNameComparison:
    """The agreement and the words it was decided on."""

    agreement: CaseNameAgreement
    written: str | None
    recorded: str | None
    written_sides: tuple[frozenset[str], ...]
    recorded_sides: tuple[frozenset[str], ...]

    @property
    def reason(self) -> str:
        """One sentence a reader can check the decision against."""
        if self.agreement is CaseNameAgreement.EXACT:
            return "The written and recorded case names are the same after normalisation."
        if self.agreement is CaseNameAgreement.CONTAINED:
            return (
                "Every distinctive word the filing wrote appears on the matching side of the record's name."
            )
        if self.agreement is CaseNameAgreement.UNAVAILABLE:
            return "One of the two names is missing or has no distinctive word to compare."
        return "A word the filing wrote appears on no side of the record's name."


def written_case_name(plaintiff: str | None, defendant: str | None) -> str | None:
    """The case name a citation states, tolerating a single-party caption."""
    if plaintiff and defendant:
        return f"{plaintiff} v. {defendant}"
    return plaintiff or defendant or None


def compare_case_names(
    *,
    plaintiff: str | None,
    defendant: str | None,
    recorded: str | None,
) -> CaseNameComparison:
    """Compare the parties a filing wrote against a record's case name."""
    written = written_case_name(plaintiff, defendant)
    written_sides = tuple(frozenset(name_words(part)) for part in (plaintiff, defendant) if name_words(part))
    recorded_sides = tuple(
        frozenset(_with_joins(part)) for part in _SIDE_SEPARATOR.split(recorded or "") if name_words(part)
    )
    acronyms = frozenset(
        match.group(0).lower() for part in (plaintiff, defendant) if part for match in _ACRONYM.finditer(part)
    )
    initials = tuple(_initials(part) for part in _SIDE_SEPARATOR.split(recorded or "") if name_words(part))
    comparison = CaseNameComparison(
        agreement=CaseNameAgreement.UNAVAILABLE,
        written=written,
        recorded=recorded,
        written_sides=written_sides,
        recorded_sides=recorded_sides,
    )
    if written is None or recorded is None:
        return comparison
    if _fold(written) == _fold(recorded):
        return _with(comparison, CaseNameAgreement.EXACT)
    if not written_sides or not recorded_sides:
        return comparison
    recorded_with_initials = tuple(zip(recorded_sides, initials, strict=True))
    if _sides_contained(written_sides, recorded_with_initials, acronyms):
        return _with(comparison, CaseNameAgreement.CONTAINED)
    return _with(comparison, CaseNameAgreement.MISMATCH)


def _sides_contained(
    written: tuple[frozenset[str], ...],
    recorded: tuple[tuple[frozenset[str], str], ...],
    acronyms: frozenset[str],
) -> bool:
    """Whether each written side is covered by a distinct recorded side, in some order."""
    if len(written) > len(recorded):
        # A two-sided name written against a one-sided record: `In re Golden`
        # holds one party, and `Golden v. State` is not it.
        return False

    def covers(side: tuple[frozenset[str], str], words: frozenset[str]) -> bool:
        return _side_covers(side[0], side[1], words, acronyms)

    if len(written) == 1:
        return any(covers(side, written[0]) for side in recorded)
    straight = covers(recorded[0], written[0]) and covers(recorded[1], written[1])
    swapped = covers(recorded[0], written[1]) and covers(recorded[1], written[0])
    return straight or swapped


def _side_covers(
    recorded: frozenset[str], initials: str, written: frozenset[str], acronyms: frozenset[str]
) -> bool:
    """Whether a record side covers every written word, an acronym by the record's initials.

    `FDIC` is not a prefix of anything in `Federal Deposit Insurance Corp.`,
    but it is the initials of it. A written word the filing set in capitals is
    covered when it appears, in order, in the initials of the record's side.
    """
    return bool(written) and all(
        name_covers(set(recorded), {word}) or (word in acronyms and word in initials) for word in written
    )


def _initials(recorded_side: str) -> str:
    """The first letters of every word on a record's side, generic words included."""
    return "".join(word[0] for word in ordered_words(recorded_side, minimum_length=1, keep_generic=True))


def _with_joins(recorded_side: str) -> set[str]:
    """A record side's words, plus each adjacent pair run together.

    A filing writes `JPMorgan` where the record has `JP Morgan`, or
    `MoralesQuinones` where it has `Morales-Quinones`. The joined forms are
    added to the record's side only, since that is the side that has to cover
    what the filing wrote; the pairs are built before short words are dropped,
    so `JP` survives into `jpmorgan`.
    """
    every = ordered_words(recorded_side, minimum_length=1)
    return set(name_words(recorded_side)) | {a + b for a, b in pairwise(every)}


def _fold(value: str) -> str:
    return " ".join(value.split()).casefold()


def _with(comparison: CaseNameComparison, agreement: CaseNameAgreement) -> CaseNameComparison:
    return CaseNameComparison(
        agreement=agreement,
        written=comparison.written,
        recorded=comparison.recorded,
        written_sides=comparison.written_sides,
        recorded_sides=comparison.recorded_sides,
    )
