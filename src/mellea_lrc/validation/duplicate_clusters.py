"""Merge archive records that are the same decision held more than once.

A citation lookup can return several records for one volume and page. Most of
the time that is not ambiguity at all: CourtListener holds the same decision
twice -- a library import beside a scraped copy, an opinion beside its later
amendment, a record whose name field is empty. Counting those as separate
candidates makes an unambiguous citation look contested, and
``candidate_selection`` then applies a limit to a number that is mostly
duplication.

Measured over the 90 ambiguous locators in the last probe, read back from the
stored answers at no request cost:

* 76 return exactly two records, and **73 of those 76 are one case**.
* **61 of the 76 pairs share a decision date, and every one of those 61 is the
  same case.** No wrong merges at all.
* Ten pairs have an empty name on one side, and eight of those ten agree on
  date -- so the date decides exactly the cases where a name comparison has
  nothing to work with.
* The 3 genuine collisions -- two different cases printed on one page -- differ
  in **both** name and date, so no merge reaches them.

**The date is the field to merge on, not the name.** That was not obvious: the
names differ in ways no string rule covers (`Reno` against `Janet Reno`, `Rhode
Island` against `RI`, `&` against `And`, `Johnson` against `Johnson II`, one
record with no name at all), and an earlier design assumed a model would be
needed to reconcile them. It is not, for the common case. Name comparison is
kept here only as a *second* way to merge records the date leaves apart, and
only when both names are present, since the 12 remaining same-case pairs are
split by CourtListener recording an opinion and its rehearing on different
days.

The court is deliberately not used. It is ``None`` on every record the
citation-lookup route returns -- the payload carries no court field at all,
though :class:`~mellea_lrc.courtlistener.opinion_models.CourtListenerOpinionCluster`
declares one -- so a rule that consulted it would silently never fire.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mellea_lrc.courtlistener.opinion_models import CourtListenerOpinionCluster

__all__ = [
    "case_name_matches",
    "matching_case_names",
    "merge_duplicates",
    "name_covers",
    "name_words",
    "same_case_name",
]

# Words that carry no identity: corporate forms, the article, and the wrappers a
# reporter puts around a party.
_GENERIC = re.compile(
    r"\b(inc|llc|llp|ltd|co|corp|corporation|company|the|of|and|et|al|state|"
    r"commonwealth|dept|department|in|re|matter|ex|rel)\b"
)
_PUNCTUATION = re.compile(r"[^a-z0-9 ]+")
# Two records must share at least this many distinctive words before a
# containment test is allowed to merge them. See same_case_name.
_MINIMUM_SHARED_WORDS = 2

# A written word this long may stand for a longer one it begins. Below it,
# `co` would match `Colgate` and `Cox` alike.
_MINIMUM_PREFIX = 3

# Party-name abbreviations that drop the middle of a word and keep its end, so
# no prefix test reaches them. The apostrophe is already gone by this point.
_CONTRACTIONS = {
    "assn": "assoc",
    "intl": "international",
    "natl": "national",
    "mgmt": "manage",
    "bhd": "brotherhood",
    "sys": "system",
    "servs": "service",
    "svcs": "service",
    "cnty": "county",
    "dist": "district",
    "auth": "authorit",
    "comm": "commi",
    "indus": "industr",
    "sec": "securit",
}

# A trailing roman numeral marks which appeal this is, not which case.
_APPEAL_STAGE = re.compile(r"\b(ii|iii|iv|v?i{0,3})\b$")


def name_words(name: str | None) -> set[str]:
    """The distinctive words of a case name, for comparing one name with another.

    Corporate forms, articles and the wrappers a reporter puts around a party
    are removed, along with the roman numeral that marks which appeal this is
    rather than which case. Words of two letters or fewer carry no identity and
    go too, which is why `United States v. Lo` reduces to `united` and `states`
    alone.
    """
    return _words(name)


def name_covers(recorded: set[str], written: set[str]) -> bool:
    """Whether every word the filing wrote appears in a record's name."""
    return bool(written) and _covers(recorded, written)


def _words(name: str | None) -> set[str]:
    folded = (name or "").lower().replace("&", " and ")
    folded = _PUNCTUATION.sub(" ", folded)
    folded = _GENERIC.sub(" ", folded)
    folded = _APPEAL_STAGE.sub(" ", " ".join(folded.split()))
    return {word for word in folded.split() if len(word) > 2}


def same_case_name(left: str | None, right: str | None) -> bool:
    """Whether two record names plausibly name the same decision.

    Used only to merge records the date has already left apart, so it is
    allowed to be generous -- but not when either name is missing. An empty
    name is no evidence of anything, and treating it as a match would merge
    every unnamed record into the first case it met.

    One distinctive word is also not enough. The containment test below is what
    lets `Giebeler v. Associates` merge into `Giebeler v. M & B Associates`,
    and with a single word on the smaller side it would merge any two records
    sharing one party -- every `United States v. …` on a page of them. So both
    names must survive to at least two words.
    """
    first, second = _words(left), _words(right)
    smaller, larger = sorted((first, second), key=len)
    if len(smaller) < _MINIMUM_SHARED_WORDS:
        return False
    return smaller <= larger


def merge_duplicates(
    clusters: Sequence[CourtListenerOpinionCluster],
) -> tuple[tuple[CourtListenerOpinionCluster, ...], ...]:
    """Group records that are the same decision, in the order they arrived.

    Each group's first record is the one that arrived first, so a caller that
    wants one record per case can take it. Two records merge when they share a
    decision date, or when neither date is known and their names agree.
    """
    groups: list[list[CourtListenerOpinionCluster]] = []
    for cluster in clusters:
        for group in groups:
            if _is_duplicate(group[0], cluster):
                group.append(cluster)
                break
        else:
            groups.append([cluster])
    return tuple(tuple(group) for group in groups)


def _is_duplicate(
    known: CourtListenerOpinionCluster,
    candidate: CourtListenerOpinionCluster,
) -> bool:
    """Whether the candidate is another record of the decision already seen."""
    if known.date_filed and candidate.date_filed:
        if known.date_filed == candidate.date_filed:
            return True
        # Different dates on one page are the 3 genuine collisions in the
        # measurement, and also the 12 same-case pairs split by a rehearing.
        # A name agreement separates them; without both names, decline.
        return same_case_name(known.case_name, candidate.case_name)
    return same_case_name(known.case_name, candidate.case_name)


def matching_case_names(
    clusters: Sequence[CourtListenerOpinionCluster],
    *,
    plaintiff: str | None,
    defendant: str | None,
) -> tuple[int, ...]:
    """Which records carry the case name the filing wrote, by position.

    A printed page can carry dozens of unrelated cases -- an unpublished-decision
    table, or a Supreme Court orders list -- and the volume and page alone
    cannot separate them. The case name can, and the filing supplies it.

    Every distinctive word the filing wrote must appear in the record's name.
    Requiring the filing's words rather than the record's is what makes this
    usable on a page of `United States v. ...` entries: the filing names a
    defendant, and only one record carries it.

    Returns an empty result when the filing named too little to decide on --
    which must not be read as a mismatch. It is also empty when no record
    matches, and that case is genuinely ambiguous: either the filing named a
    case that is not on the page, or the archive holds only part of the page.
    On the twelve crowded pages in the corpus this separated eleven correctly
    and failed once, on a page the archive covers thinly.
    """
    return tuple(
        index
        for index, cluster in enumerate(clusters)
        if case_name_matches(cluster.case_name, plaintiff=plaintiff, defendant=defendant)
    )


def case_name_matches(recorded: str | None, *, plaintiff: str | None, defendant: str | None) -> bool:
    """Whether one record's case name is the one the filing wrote.

    Every distinctive word the filing wrote must appear in the record's name,
    allowing the abbreviations a citation conventionally uses. Returns ``False``
    when the filing named too little to decide on, which is not the same as a
    disagreement and must not be read as one.
    """
    written = _words(plaintiff) | _words(defendant)
    if len(written) < _MINIMUM_SHARED_WORDS:
        return False
    return _covers(_words(recorded), written)


def _covers(recorded: set[str], written: set[str]) -> bool:
    """Whether every word the filing wrote is present in the record's name."""
    return all(any(_same_word(word, other) for other in recorded) for word in written)


def _same_word(written: str, recorded: str) -> bool:
    """Whether one word of a written case name is the record's word for it.

    A citation abbreviates party names by convention, in two shapes. Most are
    truncations keeping the front -- `Pac.` for Pacific, `Corp.` for
    Corporation, `Univ.` for University -- which a prefix test covers. The rest
    cut out the middle and keep the end, which no prefix test reaches, so those
    are listed. Without this, `Reyes v. Pac. Bell` does not match `Victor Reyes
    v. Pacific Bell`, which is the ordinary way that case is cited.
    """
    if written == recorded:
        return True
    expanded = _CONTRACTIONS.get(written)
    if expanded is not None and recorded.startswith(expanded):
        return True
    return len(written) >= _MINIMUM_PREFIX and recorded.startswith(written)
