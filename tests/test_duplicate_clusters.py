"""Tests for merging archive records that are one decision held twice.

Every name here is quoted from a real pair the citation lookup returned, so a
change that breaks one is a change against what the archive actually contains.
"""

import pytest

from mellea_lrc.courtlistener.opinion_models import CourtListenerOpinionCluster
from mellea_lrc.validation.duplicate_clusters import merge_duplicates, same_case_name


def _cluster(name: str, date: str | None = None) -> CourtListenerOpinionCluster:
    return CourtListenerOpinionCluster(case_name=name, date_filed=date)


def test_two_records_sharing_a_date_are_one_case() -> None:
    """The date is the field that decides, and it decides 61 of 76 pairs.

    It is not the name. The names differ in ways no string rule covers, and
    the date is right every time it fires -- no wrong merges in any of the 61.
    """
    records = [
        _cluster("Grasty v. Amalgamated Clothing & Textile Workers Uni", "1987-08-31"),
        _cluster("Grasty v. Amalgamated Clothing And Textile Workers U", "1987-08-31"),
    ]

    assert len(merge_duplicates(records)) == 1


def test_a_record_with_no_name_still_merges_on_its_date() -> None:
    """Ten of the 76 pairs have an empty name on one side.

    Eight of those ten agree on date, so the date decides exactly the cases
    where comparing names has nothing to work with.
    """
    records = [_cluster("Local Joint Executive Board of Culinary", "2001-04-11"), _cluster("", "2001-04-11")]

    assert len(merge_duplicates(records)) == 1


def test_two_different_cases_on_one_page_are_kept_apart() -> None:
    """Three of the 76 are genuine collisions, and all three differ in both.

    A printed page can carry the end of one case and the start of another, so
    this has to keep working; it is what makes merging safe at all.
    """
    records = [
        _cluster("State ex rel. Department of Human Services v. Brock", "1988-10-13"),
        _cluster("Mindemann v. Independent School District No. 6", "1989-04-04"),
    ]

    assert len(merge_duplicates(records)) == 2


def test_an_opinion_and_its_rehearing_merge_on_the_name() -> None:
    """Twelve pairs are one case that the archive dated twice.

    CourtListener records an opinion and its later amendment separately, so
    the date splits them and the name has to put them back.
    """
    records = [
        _cluster("Ultramercial, LLC v. Hulu, LLC", "2011-09-15"),
        _cluster("Ultramercial, LLC v. Hulu, LLC", "2011-03-18"),
    ]

    assert len(merge_duplicates(records)) == 1


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Giebeler v. M & B Associates", "Giebeler v. Associates"),
        ("Johnson v. Karnes", "Johnson II v. Karnes"),
        ("Warrick v. General Electric Co.", "Warrick v. General Electric"),
    ],
)
def test_a_name_may_be_shortened_and_still_be_the_same_case(left: str, right: str) -> None:
    assert same_case_name(left, right)


def test_an_abbreviated_word_is_not_recognised_and_that_is_left_alone() -> None:
    """`Pub Ctzn` and `Public Citizen` are the same party and do not merge here.

    Recognising that would need per-word abbreviation matching, which is where
    merging starts joining cases that differ. The pair is one of 15 whose dates
    also differ, so it stays two candidates and gets evaluated as two -- worse
    than merging it, and much better than merging something it should not.
    """
    assert not same_case_name("Public Citizen, Inc. v. U.S. Dept HHS", "Pub Ctzn Inc v. HHS")


def test_one_shared_word_is_not_enough_to_merge() -> None:
    """A page of unpublished decisions is full of `United States v. …`.

    The containment test is what lets a shortened name merge into a longer
    one, and with a single word on the smaller side it would merge every case
    on such a page into the first one.
    """
    assert not same_case_name("United States v. Luna", "United States v. Chambers")
    assert not same_case_name("Case 0", "Case 1")


def test_a_missing_name_is_no_evidence_of_a_match() -> None:
    """Otherwise every unnamed record joins whichever case it met first."""
    assert not same_case_name("", "Grasty v. Amalgamated")
    assert not same_case_name(None, None)
    assert (
        len(
            merge_duplicates(
                [_cluster("Essex Chemical Corp. v. Ruckelshaus", "1973-09-10"), _cluster("", "1973-10-03")]
            )
        )
        == 2
    )
