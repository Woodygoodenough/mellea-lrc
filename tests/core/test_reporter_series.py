"""Tests for detecting citations to reporter series that were never published."""

from __future__ import annotations

import pytest

from mellea_lrc.core.reporter_series import find_impossible_series


@pytest.mark.parametrize(
    ("text", "reporter", "highest"),
    [
        ("See 531 N.E.4th 224, 242 (7th Cir. 1988).", "N.E.4th", 3),
        ("423 F.5th 938, 965 (7th Cir. 2000)", "F.5th", 4),
        ("921 Cal. Rptr. 4th 980, 982 (Cal. Ct. App. 1988)", "Cal. Rptr. 4th", 3),
        ("768 N.Y.S.4th 769, 772 (E.D. Va. 1986)", "N.Y.S.4th", 3),
        ("694 F. Supp. 4th 869, 891 (5th Cir. 1991)", "F. Supp. 4th", 3),
    ],
)
def test_a_series_beyond_what_the_family_published_is_reported(
    text: str,
    reporter: str,
    highest: int,
) -> None:
    """No case can sit at an address in a series that was never printed."""
    (found,) = find_impossible_series(text)

    assert found.reporter == reporter
    assert found.highest_published_series == highest


def test_the_matched_span_locates_the_citation_in_the_text() -> None:
    """A caller has to be able to point at what it is rejecting."""
    text = "Relying on 531 N.E.4th 224 (7th Cir. 1988), the court held otherwise."

    (found,) = find_impossible_series(text)

    assert text[found.start : found.end] == found.text
    assert found.text == "531 N.E.4th 224"


def test_a_short_form_is_reported_too() -> None:
    """A fabricated series is fabricated in either form."""
    (found,) = find_impossible_series("531 N.E.4th at 242")

    assert found.series == 4


@pytest.mark.parametrize(
    "text",
    [
        "410 U.S. 113 (1973)",
        "550 U.S. 544, 560 (2007)",
        "382 F. Supp. 2d 1173, 1176 (N.D. Cal. 2004)",
        "121 Cal.Rptr.3d 819",
        "22 I. & N. Dec. 1328, 1330",
        "2016 WL 7189917 (Del. Dec. 12, 2016)",
        "969 N.E.2d 1118 (Mass. 2012)",
    ],
)
def test_an_ordinary_citation_is_left_alone(text: str) -> None:
    """The rule is worth nothing if it fires on real citations."""
    assert find_impossible_series(text) == ()


def test_a_series_the_family_reached_recently_is_not_fabricated() -> None:
    """The Federal Reporter began a fourth series in 2021.

    The published series come from the reporter database rather than a list
    written here, so a new one is known as soon as that dependency is updated.
    Hard-coding what exists is how a rule like this starts rejecting real
    citations some years after it is written.
    """
    assert find_impossible_series("993 F.4th 100 (9th Cir. 2021)") == ()
    assert find_impossible_series("993 F.5th 100 (9th Cir. 2021)") != ()


@pytest.mark.parametrize("text", ["701 F. Supp 2d at 917", "151 Fed 2nd 240"])
def test_a_real_citation_written_loosely_is_not_fabricated(text: str) -> None:
    """Both of these were reported as impossible by earlier versions of the index.

    The first drops the period after `Supp`, which made `F. Supp` a family of
    its own holding only a first series. The second uses `Fed.`, which the
    database registers as another way of writing `F.`; giving the variation its
    own entry left it without the Federal Reporter's later series. Neither is a
    fabrication, and a rule that rejects sloppy-but-real citations is worse than
    no rule.
    """
    assert find_impossible_series(text) == ()


def test_an_unknown_reporter_is_not_called_fabricated() -> None:
    """The database is extensive but not exhaustive.

    A name it does not carry is as easily a gap in the database as an invention,
    so the rule reports only an impossible series of a family that exists.
    """
    assert find_impossible_series("12 Nonesuch Rptr. 3d 45 (2011)") == ()


def test_the_reason_names_the_family_and_both_series() -> None:
    """A verdict a reader cannot check is not much use."""
    (found,) = find_impossible_series("531 N.E.4th 224")

    assert found.reason == ("N.E.4th names series 4 of N.E., which was published only through series 3.")


def test_a_publisher_suffix_does_not_hide_the_series() -> None:
    """The database names some editions `A.F.T.R.2d (RIA)`, and the series must survive it.

    A series suffix has to end the string to be read, so a trailing publisher
    hid it. Those families were recorded as reaching only a first series, and
    every real second-series citation to them was reported as impossible --
    which is how the rule's only firing over 120 court orders came to be a
    false positive on two real reporters.
    """
    assert find_impossible_series("105 A.F.T.R.2d 2010") == ()
    assert find_impossible_series("69 U.C.C. Rep. Serv. 2d 890") == ()


def test_the_publisher_fix_does_not_blunt_the_rule() -> None:
    found = find_impossible_series("531 N.E.4th 224")

    assert len(found) == 1
    assert found[0].series == 4
    assert found[0].highest_published_series == 3
