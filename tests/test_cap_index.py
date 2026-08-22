"""Tests for the offline Caselaw Access Project reporter index.

These load `tests/fixtures/cap`, a two-case slice of the real archive index for
volume 489 of the United States Reports, so the suite stays offline. The slice
is real data rather than an invented example: `City of Canton v. Harris` runs
from page 378 to 400, and it is the case that made this index worth building.
"""

from pathlib import Path

import pytest

from mellea_lrc.caselaw import CapIndex, PageOutcome, reporter_slug, volume_metadata_url

_FIXTURES = Path(__file__).parent / "fixtures" / "cap"


@pytest.fixture
def index(tmp_path: Path) -> CapIndex:
    built = CapIndex(cache_dir=tmp_path, allow_fetch=False)
    built.load_file("us", "489", _FIXTURES / "us-489-slice.json")
    return built


def test_a_page_that_starts_a_case_is_reported_as_one(index: CapIndex) -> None:
    verdict = index.page("us", "489", "378")

    assert verdict.outcome is PageOutcome.STARTS_A_CASE
    assert verdict.case is not None
    assert verdict.case.name == "City of Canton v. Harris"
    assert not verdict.contradicts_locator


def test_a_page_inside_a_case_names_the_case_it_belongs_to(index: CapIndex) -> None:
    """This is what the index is for, and a lookup service cannot answer it.

    A filing cited `489 U.S. 379`. CourtListener holds no case starting there
    and returns nothing, which under this project's rules concludes nothing.
    The archive records page ranges, so it can say that page 379 is inside
    `City of Canton v. Harris`, which starts at 378 -- a real case cited at the
    wrong first page, which is positive evidence rather than an absence.
    """
    verdict = index.page("us", "489", "379")

    assert verdict.outcome is PageOutcome.INSIDE_A_CASE
    assert verdict.case is not None
    assert verdict.case.name == "City of Canton v. Harris"
    assert verdict.case.first_page == 378
    assert verdict.contradicts_locator


def test_a_page_no_case_covers_concludes_nothing(index: CapIndex) -> None:
    """The archive is one collection with a known end date.

    Its silence means what a CourtListener miss means. Reporting it as a defect
    would be the same mistake in a new place.
    """
    verdict = index.page("us", "489", "9999")

    assert verdict.outcome is PageOutcome.NO_CASE_COVERS_IT
    assert verdict.case is None
    assert not verdict.contradicts_locator


def test_a_volume_the_archive_lacks_says_so_rather_than_guessing(tmp_path: Path) -> None:
    """The archive stops around 2020, so a recent volume is simply not there.

    That is a statement about the index and never about the citation, so it has
    its own outcome rather than being folded in with a page nothing covers.
    """
    empty = CapIndex(cache_dir=tmp_path, allow_fetch=False)

    verdict = empty.page("us", "587", "460")

    assert verdict.outcome is PageOutcome.VOLUME_UNAVAILABLE
    assert not verdict.contradicts_locator


def test_star_pagination_is_not_treated_as_a_printed_page(index: CapIndex) -> None:
    """`*16` pinpoints a slip opinion and has no place in a printed page range."""
    assert index.page("us", "489", "*16").outcome is PageOutcome.NO_CASE_COVERS_IT


@pytest.mark.parametrize(
    ("reporter", "expected"),
    [
        ("F.2d", "f2d"),
        ("F. Supp.", "f-supp"),
        ("A.D.3d", "ad3d"),
        ("N.E.2d", "ne2d"),
        ("F. App'x", "f-appx"),
        ("U.S.", "us"),
        ("N.C. App.", "nc-app"),
        ("Cal. App. 4th", "cal-app-4th"),
    ],
)
def test_a_reporter_maps_to_the_name_the_archive_publishes(reporter: str, expected: str) -> None:
    """A period inside an abbreviation closes up; a space between them dashes.

    `F.2d` is `f2d` and `A.D.3d` is `ad3d`, while `F. Supp.` is `f-supp` and
    `N.C. App.` is `nc-app`. Treating every period as a space instead gets
    `n-c-app`, which is not published and silently loses the reporter.
    """
    published = {"f2d", "f-supp", "ad3d", "ne2d", "f-appx", "us", "nc-app", "cal-app-4th"}

    assert reporter_slug(reporter, published) == expected


def test_a_reporter_that_postdates_the_archive_is_absent_too() -> None:
    """`F.4th` began in 2021, after the archive stopped. There is no directory.

    Reported the same way as a vendor identifier, because the caller's next
    move is the same: this index has nothing to say.
    """
    assert reporter_slug("F.4th", {"f2d", "f3d", "us"}) is None


def test_a_vendor_identifier_is_not_a_reporter() -> None:
    """`2016 WL 9137645` names a Westlaw record, not a volume of a reporter.

    Nearly half the citations the locator probe could not resolve are of this
    kind, and no free archive can hold them, so returning `None` here is the
    honest answer rather than a lookup that was always going to fail.
    """
    published = {"f2d", "us", "wash"}

    assert reporter_slug("WL", published) is None
    assert reporter_slug("U.S. Dist. LEXIS", published) is None


def test_the_volume_url_matches_the_archive_layout() -> None:
    assert volume_metadata_url("ad3d", "139") == "https://static.case.law/ad3d/139/CasesMetadata.json"
