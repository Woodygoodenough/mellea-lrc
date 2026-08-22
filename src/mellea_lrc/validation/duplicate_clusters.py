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

__all__ = ["merge_duplicates", "same_case_name"]

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

# A trailing roman numeral marks which appeal this is, not which case.
_APPEAL_STAGE = re.compile(r"\b(ii|iii|iv|v?i{0,3})\b$")


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
