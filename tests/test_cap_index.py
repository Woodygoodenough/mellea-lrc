"""Tests for the offline Caselaw Access Project reporter index.

These load `tests/fixtures/cap`, a two-case slice of the real archive index for
volume 489 of the United States Reports, so the suite stays offline. The slice
is real data rather than an invented example: `City of Canton v. Harris` runs
from page 378 to 400, and it is the case that made this index worth building.
"""

import json
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


def test_a_scanned_page_number_is_corrected_to_the_printed_one(tmp_path: Path) -> None:
    """In a few volumes `first_page` holds the page of the scan, not of the book.

    Volume 377 of the United States Reports is one: every case is offset by a
    constant 132, so `Missouri Pacific Railroad v. Elmore & Stahl` carries
    `first_page` 266 while its own citation is `377 U.S. 134`.

    Uncorrected this is not a missed answer but a confident wrong one --
    `377 U.S. 408` was reported as sitting inside a different case entirely.
    Anchoring on the page in the case's own citation for the volume fixes it,
    and across 686 volumes it removed four false findings and created none.
    """
    index = CapIndex(cache_dir=tmp_path, allow_fetch=False)
    index.load_file("us", "377", _FIXTURES / "us-377-slice.json")

    verdict = index.page("us", "377", "408")

    assert verdict.outcome is PageOutcome.STARTS_A_CASE
    assert verdict.case is not None
    assert verdict.case.name == "Donovan v. City of Dallas"
    assert not verdict.contradicts_locator


def test_the_span_length_survives_the_correction(tmp_path: Path) -> None:
    """Only the origin is wrong, so the number of pages is kept as recorded."""
    index = CapIndex(cache_dir=tmp_path, allow_fetch=False)
    index.load_file("us", "377", _FIXTURES / "us-377-slice.json")

    verdict = index.page("us", "377", "135")

    assert verdict.outcome is PageOutcome.INSIDE_A_CASE
    assert verdict.case is not None
    assert verdict.case.first_page == 134
    assert verdict.case.last_page > verdict.case.first_page


@pytest.mark.parametrize(
    ("reporter", "expected"),
    [("N.Y.2d", "ny-2d"), ("N.C.App.", "nc-app"), ("Fed. Appx.", "f-appx")],
)
def test_a_reporter_the_rule_cannot_predict_is_listed(reporter: str, expected: str) -> None:
    """The archive's own naming is not fully consistent, so three are aliased.

    `N.Y.2d` takes a dash the rule cannot derive, `N.C.App.` written closed up
    gives `ncapp`, and `Fed. Appx.` is filed under the modern `f-appx`. Each
    was checked against the published directory listing rather than guessed.
    """
    assert reporter_slug(reporter, {"ny-2d", "nc-app", "f-appx", "f2d"}) == expected


def test_two_cases_claiming_one_page_concludes_nothing(tmp_path: Path) -> None:
    """Cases share a page routinely; spans that genuinely overlap are different.

    A shared page is one case ending partway down where the next begins, and
    the archive records it by letting spans touch. Overlapping spans mean the
    archive does not agree with itself about whose page it is, which is 1.5% of
    adjacent pairs -- and is also the shape a volume takes when its recorded
    pages are wrong in bulk. Either way nothing may be concluded, so this is a
    second guard against the scanned-page problem, independent of the
    correction for it.
    """
    overlapping = json.dumps(
        [
            {
                "name_abbreviation": "Maestracci v. Helly Nahmad Gallery",
                "first_page": "405",
                "last_page": "409",
                "decision_date": "2017-11-21",
                "court": {"name_abbreviation": "N.Y. App. Div."},
                "citations": [{"type": "official", "cite": "155 A.D.3d 405"}],
            },
            {
                "name_abbreviation": "Korff v. Corbett",
                "first_page": "405",
                "last_page": "411",
                "decision_date": "2017-11-21",
                "court": {"name_abbreviation": "N.Y. App. Div."},
                "citations": [{"type": "official", "cite": "155 A.D.3d 405"}],
            },
        ]
    )
    path = tmp_path / "overlap.json"
    path.write_text(overlapping)
    index = CapIndex(cache_dir=tmp_path, allow_fetch=False)
    index.load_file("ad3d", "155", path)

    verdict = index.page("ad3d", "155", "407")

    assert verdict.outcome is PageOutcome.AMBIGUOUS_PAGE
    assert verdict.case is None
    assert not verdict.contradicts_locator


def _volume_963(tmp_path: Path) -> CapIndex:
    index = CapIndex(cache_dir=tmp_path, allow_fetch=False)
    index.load_file("f2d", "963", _FIXTURES / "f2d-963-slice.json")
    return index


def test_every_case_beginning_on_a_page_is_returned(tmp_path: Path) -> None:
    """Several cases routinely start on one page, and picking one accuses a filing.

    `963 F.2d 1258` begins both `United States v. Fine`, which occupies that
    page alone, and `Ferdik v. Bonzelet`, which runs to 1264. Returning the
    first one found told a filing that correctly cited Ferdik that the page
    belongs to Fine -- a false accusation against a well-known citation, and
    the same shape caught `Steckman v. Hart Brewing` and `Octocom Systems`.
    """
    verdict = _volume_963(tmp_path).page("f2d", "963", "1258")

    assert verdict.outcome is PageOutcome.STARTS_A_CASE
    assert {case.name for case in verdict.cases} == {"United States v. Fine", "Ferdik v. Bonzelet"}


def test_a_case_with_an_unreadable_last_page_is_kept(tmp_path: Path) -> None:
    """`Sher v. Johnson` carries a last page of `1366-1376`.

    Dropping the case for that is worse than not knowing where it ends: the
    case vanishes, its first page reads as belonging to whatever ran up to it,
    and a correct citation is contradicted. It is treated as a single page
    instead, which understates the span and never invents one.
    """
    verdict = _volume_963(tmp_path).page("f2d", "963", "1357")

    assert verdict.outcome is PageOutcome.STARTS_A_CASE
    assert verdict.case is not None
    assert verdict.case.name == "Sher v. Johnson"


def test_an_abbreviation_shared_with_another_reporter_is_declined() -> None:
    """`70 O.S. 5` is the Oklahoma Statutes, and `O.S.` also names Ohio State Reports.

    Resolving an unplaceable abbreviation through a reporter database's
    canonical name looks like an obvious improvement. It is not: it sends a
    citation to the Oklahoma school code into the Ohio reports, where the
    archive answers confidently and wrongly that it sits inside *State v.
    Schiller*, 70 Ohio St. 1 (1904). Declining is the point of this function.
    """
    assert reporter_slug("O.S.", {"ohio-st", "us", "f2d"}) is None
    assert reporter_slug("CMR", {"ct-mart-rep", "us", "f2d"}) is None
