"""Check a filing's case name against the case the printed reporter has there.

The pipeline already compares a case name against a CourtListener record. This
does the same thing offline, against Harvard's digitisation of the printed
reporters, which costs no request allowance and covers volumes the lookup
service answers differently -- see :mod:`~mellea_lrc.caselaw.cap_index`.

**The comparison has three outcomes, not two**, and that is the whole design.
Legal citation abbreviates constantly and in both directions: a filing writes
``Landis v. N. Am. Co.`` where the reporter has ``Landis v. North American
Co.``, and writes ``Doe v. George Washington Univ.`` where the reporter has
``Doe v. George Wash. Univ.``. A rule with only agree and disagree calls both
of those disagreements, and a checker built on it accuses a filing of
miscitation for abbreviating a party name.

So a word that fails to match is weighed by what kind of word it is:

* A **spelled-out word that is simply absent** from the record is evidence.
  ``Cadle`` and ``Ayala`` are absent from ``Ramirez v. City of New York``, and
  no abbreviation rule reaches across that.
* An **abbreviation that fails to match is not evidence.** ``Mtge.`` does not
  prefix ``Mortgage``, ``CFTC`` does not prefix ``Commodity Futures Trading
  Commission``, and ``N. Am.`` disappears entirely under normalisation. None of
  those means the filing named a different case.

Where only abbreviations fail, the answer is :attr:`NameVerdict.UNDECIDED`.
That is not a hedge -- it is the same rule the rest of the project runs on,
that an absence of evidence is not evidence.

Measured over the 26 test filings, using the case names annotated verbatim from
the filings themselves rather than a parse of them, so a disagreement cannot be
an extraction error:

=========================  =====
agrees                       272
the archive cannot speak     186
undecided                     74
**disagrees**              **53** (32 distinct citations)
=========================  =====

Reading those 32, about a third are still artifacts this does not catch:
``Pioneer Inv. Servs.`` against ``Pioneer Investment Services`` (an
abbreviation that drops a letter from the middle), ``Matter of M4 Enters.``
against ``In re M4 Enterprises`` (two names for the same procedural form),
``Rufo v. Inmates of Suffock County Jail`` against ``Suffolk`` (a misspelling
in the filing).

The rest are genuinely different cases, and several are corroborated
elsewhere: ``139 A.D.3d 695`` is *Ramirez v. City of New York* in this archive,
in CourtListener, and in the New York official reports, where the filing wrote
*Cadle Co. v. Ayala*.

So the disagreement count is an **upper bound on the defect count**, and the
right use of this check is to put a small, ranked list of citations in front of
a person, not to report a verdict on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from mellea_lrc.caselaw.cap_index import reporter_slug

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mellea_lrc.caselaw.cap_index import CapCase, CapIndex

__all__ = ["CaseNameFinding", "NameVerdict", "check_case_name", "compare_case_name"]

# Kept so an abbreviation's trailing period survives to be read as one.
_PUNCTUATION = re.compile(r"[^a-z0-9. ]+")

# Words carrying no identity: corporate forms, articles, and the wrappers a
# reporter puts around a party.
_GENERIC = frozenset(
    {
        "inc",
        "llc",
        "llp",
        "ltd",
        "co",
        "corp",
        "corporation",
        "company",
        "the",
        "of",
        "and",
        "et",
        "al",
        "state",
        "commonwealth",
        "dept",
        "department",
        "in",
        "re",
        "matter",
        "ex",
        "rel",
        "no",
    }
)

# A spelled-out word is at least this long. Below it, a word is treated as an
# abbreviation whether or not it kept its period -- `Am`, `Ct` and `Bd` are
# abbreviations that often lose the dot in extraction.
MINIMUM_SPELLED_OUT = 4

# `v.`, `vs.` and the bare `v` that survives some extractions.
_PARTY_SEPARATOR = re.compile(r"\s+v[.s]?\.?\s+", re.IGNORECASE)


class NameVerdict(str, Enum):
    """What comparing a written case name against a record established."""

    AGREES = "agrees"
    """Every word the filing wrote is present in the record's name."""

    DISAGREES = "disagrees"
    """A spelled-out word the filing wrote is absent from the record.

    Evidence that the citation names a different case than the one printed at
    that page. Not proof: see the module docstring on what survives reading.
    """

    UNDECIDED = "undecided"
    """Only abbreviations failed to match, or the filing named too little.

    Says nothing about the citation. An abbreviation that does not match is a
    limit of the comparison, not a finding about the filing.
    """


@dataclass(frozen=True, slots=True)
class CaseNameFinding:
    """One citation's case name, compared with the reporter's."""

    written: str
    """The case name as the filing wrote it."""
    case: CapCase
    """The case the printed reporter has at that volume and page."""
    verdict: NameVerdict

    @property
    def is_defect(self) -> bool:
        """Whether this is worth putting in front of a person.

        Deliberately not "whether this is a defect": the count is an upper
        bound, and about a third of the disagreements on the test filings are
        abbreviations and typos rather than different cases.
        """
        return self.verdict is NameVerdict.DISAGREES


def _tokens(name: str | None) -> list[tuple[str, bool]]:
    """Each identity-bearing word, with whether it is an abbreviation.

    Three things mark an abbreviation, and the case of the original is one of
    them, so the folding happens per word rather than up front. `CFTC` and
    `FDIC` are four letters with no period -- indistinguishable from a spelled
    out word once lowercased, and an acronym that fails to match must never
    read as evidence that the filing named a different case.
    """
    cleaned = _PUNCTUATION.sub(" ", (name or "").replace("&", " and "))
    tokens = []
    for raw in cleaned.split():
        word = raw.strip(".").lower()
        if not word or word in _GENERIC:
            continue
        acronym = raw.strip(".").isupper() and len(word) > 1
        tokens.append((word, acronym or raw.endswith(".") or len(word) < MINIMUM_SPELLED_OUT))
    return tokens


def _present(word: str, recorded: set[str]) -> bool:
    """Whether a written word appears in the record, allowing either to abbreviate.

    The abbreviating runs both ways. A filing writes `Univ. of Oregon` where the
    reporter has `Univ. of Or.`, and `George Washington Univ.` where it has
    `George Wash. Univ.`. Testing only that the written word begins the recorded
    one calls the second of those a disagreement.
    """
    return any(other == word or other.startswith(word) or word.startswith(other) for other in recorded)


def compare_case_name(written: str | None, recorded: str | None) -> NameVerdict:
    """Compare a written case name with a reporter's, in three outcomes."""
    recorded_words = {word for word, _ in _tokens(recorded)}
    sides = [side for side in _PARTY_SEPARATOR.split(written or "", maxsplit=1) if side.strip()]
    if not sides or not recorded_words:
        return NameVerdict.UNDECIDED

    verdicts = [_compare_party(side, recorded_words) for side in sides]
    if NameVerdict.DISAGREES in verdicts:
        return NameVerdict.DISAGREES
    # Both sides of a `v.` have to be accounted for. One party agreeing while
    # the other is unreadable is not agreement -- half a case name matches many
    # cases, which is how `United States v. ...` swallows a page of them.
    expected_sides = 2
    if len(verdicts) == expected_sides and all(v is NameVerdict.AGREES for v in verdicts):
        return NameVerdict.AGREES
    return NameVerdict.UNDECIDED


def _compare_party(written: str, recorded: set[str]) -> NameVerdict:
    parts = _tokens(written)
    if not parts:
        return NameVerdict.UNDECIDED
    missing = [(word, abbreviated) for word, abbreviated in parts if not _present(word, recorded)]
    if not missing:
        return NameVerdict.AGREES
    if any(not abbreviated for _, abbreviated in missing):
        return NameVerdict.DISAGREES
    return NameVerdict.UNDECIDED


def check_case_name(
    index: CapIndex,
    *,
    written_name: str | None,
    volume: str,
    reporter: str,
    page: str,
    known_reporters: Iterable[str],
) -> CaseNameFinding | None:
    """Compare one citation's written case name with the printed reporter's.

    Returns ``None`` when the archive cannot speak -- it does not publish the
    reporter, does not hold the volume, or has no case at the page. Those are
    statements about the archive and never about the citation.
    """
    slug = reporter_slug(reporter, known_reporters)
    if slug is None or not volume.isdigit():
        return None
    verdict = index.page(slug, volume, page)
    if verdict.case is None:
        return None
    return CaseNameFinding(
        written=written_name or "",
        case=verdict.case,
        verdict=compare_case_name(written_name, verdict.case.name),
    )
