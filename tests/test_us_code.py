"""Tests for the United States Code existence/in-force index.

All of these load ``tests/fixtures/us_code``, a hand-trimmed fixture in the
shape of the real USLM release (see the fixture file's own comment), never
the multi-megabyte title downloads this module was measured against -- so the
suite stays offline and fast.
"""

from pathlib import Path

import pytest

from mellea_lrc.statutes.us_code import (
    ProvisionStatus,
    UsCodeIndex,
    _natural_key,
    _normalize_section,
    title_zip_url,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "us_code"


@pytest.fixture
def index() -> UsCodeIndex:
    return UsCodeIndex.from_paths([_FIXTURES / "usc99_sample.xml", _FIXTURES / "usc07_sample.zip"])


def test_an_in_force_section_exists_and_is_in_force(index: UsCodeIndex) -> None:
    result = index.lookup(99, "1")
    assert result.exists
    assert result.in_force
    assert result.status is None


def test_a_letter_suffixed_section_is_found(index: UsCodeIndex) -> None:
    result = index.lookup(99, "4a")
    assert result.exists
    assert result.in_force


def test_a_section_absent_from_the_loaded_title_does_not_exist(index: UsCodeIndex) -> None:
    result = index.lookup(99, "999")
    assert not result.exists
    assert not result.in_force
    assert result.status is None


def test_a_title_never_loaded_reports_every_section_as_not_existing(index: UsCodeIndex) -> None:
    result = index.lookup(28, "636")
    assert not result.exists


@pytest.mark.parametrize(
    ("section", "status"),
    [
        ("2", ProvisionStatus.REPEALED),
        ("3", ProvisionStatus.OMITTED),
        ("5", ProvisionStatus.RENUMBERED),
        ("6", ProvisionStatus.TRANSFERRED),
    ],
)
def test_a_not_in_force_status_is_reported_and_not_in_force(
    index: UsCodeIndex, section: str, status: ProvisionStatus
) -> None:
    result = index.lookup(99, section)
    assert result.exists
    assert not result.in_force
    assert result.status is status


def test_a_joint_repeal_registers_every_identifier_it_lists(index: UsCodeIndex) -> None:
    """One <section> repealing "§§ 7, 8" together indexes both 7 and 8."""
    for section in ("7", "8"):
        result = index.lookup(99, section)
        assert result.exists
        assert not result.in_force
        assert result.status is ProvisionStatus.REPEALED


def test_a_range_placeholder_covers_every_section_between_its_endpoints(index: UsCodeIndex) -> None:
    """ "§§ 30 to 33" repealed as one block covers 31 and 32, neither of which
    has its own <section> element in the fixture."""
    for section in ("30", "31", "32", "33"):
        result = index.lookup(99, section)
        assert result.exists
        assert not result.in_force
        assert result.status is ProvisionStatus.REPEALED


def test_a_range_placeholder_does_not_cover_its_neighbors(index: UsCodeIndex) -> None:
    assert not index.lookup(99, "29").exists
    assert not index.lookup(99, "34").exists


def test_a_query_hyphen_matches_an_indexed_en_dash(index: UsCodeIndex) -> None:
    """OLRC's own export uses an en dash in some identifiers; a citation writes
    an ASCII hyphen. Both must resolve to the same section."""
    result = index.lookup(99, "20-1")
    assert result.exists
    assert result.in_force


def test_loading_a_zip_finds_its_single_xml_member(index: UsCodeIndex) -> None:
    result = index.lookup(7, "136")
    assert result.exists
    assert result.in_force


def test_loading_a_zip_with_no_xml_member_is_rejected(tmp_path: Path) -> None:
    import zipfile

    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w") as archive:
        archive.writestr("readme.txt", "not xml")
    with pytest.raises(ValueError, match="expected exactly one"):
        UsCodeIndex().load_xml(empty_zip)


def test_normalize_section_folds_every_known_dash_variant_to_a_hyphen() -> None:
    for dash in "‐‑‒–—−":
        assert _normalize_section(f"2000e{dash}2") == "2000e-2"


def test_natural_key_orders_digit_runs_numerically_not_lexicographically() -> None:
    """Plain string order would put "e-10" before "e-9"; natural order must not."""
    assert _natural_key("2000e-9") < _natural_key("2000e-10")
    assert _natural_key("9") < _natural_key("15a")


def test_a_section_without_an_identifier_is_skipped(tmp_path: Path) -> None:
    """USLM should always give a <section> an identifier, but the loader must
    not crash if a hand-edited or malformed document omits one."""
    xml_path = tmp_path / "no_identifier.xml"
    xml_path.write_text(
        '<uscDoc xmlns="http://xml.house.gov/schemas/uslm/1.0">'
        "<main><section><num>1</num></section></main></uscDoc>"
    )
    index = UsCodeIndex()
    index.load_xml(xml_path)
    assert not index.lookup(1, "1").exists


def test_an_unparseable_identifier_is_skipped(tmp_path: Path) -> None:
    xml_path = tmp_path / "bad_identifier.xml"
    xml_path.write_text(
        '<uscDoc xmlns="http://xml.house.gov/schemas/uslm/1.0">'
        '<main><section identifier="not-a-uslm-identifier"><num>1</num></section></main></uscDoc>'
    )
    index = UsCodeIndex()
    index.load_xml(xml_path)
    assert not index.lookup(1, "1").exists


def test_title_zip_url_matches_the_olrc_download_shape() -> None:
    url = title_zip_url(28, release_point="119-102not101")
    assert url == (
        "https://uscode.house.gov/download/releasepoints/us/pl/119/102not101/xml_usc28@119-102not101.zip"
    )
