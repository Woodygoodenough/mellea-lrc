"""Tests for reading what a cited section string names before checking it.

These load ``tests/fixtures/us_code``, the same hand-trimmed fixture the index
tests use, so the suite stays offline.
"""

from pathlib import Path

import pytest

from mellea_lrc.statutes import ProvisionStatus, SectionForm, UsCodeIndex, resolve_section
from mellea_lrc.statutes.section_forms import MAX_ENUMERATED_RANGE

_FIXTURES = Path(__file__).parent / "fixtures" / "us_code"


@pytest.fixture
def index() -> UsCodeIndex:
    return UsCodeIndex.from_paths([_FIXTURES / "usc99_sample.xml"])


def test_a_plain_section_resolves_to_itself(index: UsCodeIndex) -> None:
    verdict = resolve_section(index, "99", "1")

    assert verdict.form is SectionForm.SECTION
    assert verdict.sections == ("1",)
    assert not verdict.is_defect


def test_a_hyphenated_span_names_every_section_it_covers(index: UsCodeIndex) -> None:
    """`§§ 2201-2202` is two sections; eyecite hands it over as one string.

    Reporting the string as absent would accuse a correct citation, and this
    is ten of the fifteen apparent absences across the project's two corpora.
    """
    verdict = resolve_section(index, "99", "2201-2202")

    assert verdict.form is SectionForm.RANGE
    assert verdict.sections == ("2201", "2202")
    assert not verdict.is_defect


def test_the_abbreviated_second_number_is_written_back_out(index: UsCodeIndex) -> None:
    """`§§ 2201-02` is the ordinary Bluebook abbreviation of `2201-2202`."""
    verdict = resolve_section(index, "99", "2201-02")

    assert verdict.form is SectionForm.RANGE
    assert verdict.sections == ("2201", "2202")


def test_a_real_hyphenated_section_is_never_reread_as_a_span(index: UsCodeIndex) -> None:
    """`20-1` is a section. So are `2000e-2` and `78u-4`, which is the point.

    The direct lookup answers first, so a hyphenated string that the Code does
    have never reaches the span branch at all.
    """
    verdict = resolve_section(index, "99", "20-1")

    assert verdict.form is SectionForm.SECTION
    assert verdict.sections == ("20-1",)


def test_a_hyphenated_string_is_a_span_only_if_the_code_agrees(index: UsCodeIndex) -> None:
    """Both endpoints have to be real sections, or nothing is being reinterpreted."""
    verdict = resolve_section(index, "99", "2201-9999")

    assert verdict.form is SectionForm.ABSENT
    assert verdict.sections == ()
    assert verdict.is_defect


def test_a_span_reports_the_sections_inside_it_that_are_not_in_force(index: UsCodeIndex) -> None:
    """A span covering a repealed section is a defect even though the span parses."""
    verdict = resolve_section(index, "99", "1-3")

    assert verdict.sections == ("1", "2", "3")
    assert verdict.not_in_force == (
        ("2", ProvisionStatus.REPEALED),
        ("3", ProvisionStatus.OMITTED),
    )
    assert verdict.is_defect


def test_a_long_span_reports_its_endpoints_rather_than_every_number(index: UsCodeIndex) -> None:
    """`29 U.S.C. §§ 2601-2654` points at a whole act, not a list of sections.

    Enumerating a span that wide would assert that each number in it is a
    section, and the Code leaves gaps.
    """
    verdict = resolve_section(index, "99", "2201-2300")

    assert verdict.form is SectionForm.RANGE
    assert verdict.sections == ("2201", "2300")
    assert 2300 - 2201 + 1 > MAX_ENUMERATED_RANGE


def test_a_missing_section_is_absent(index: UsCodeIndex) -> None:
    verdict = resolve_section(index, "99", "999")

    assert verdict.form is SectionForm.ABSENT
    assert verdict.is_defect


def test_a_letter_suffixed_miss_is_unresolved_rather_than_absent(index: UsCodeIndex) -> None:
    """In a typewritten filing every digit 1 was scanned as a lowercase l.

    `18 U.S.C. § 201` came out as `20l`, which is the same shape as the real
    `1681g` and `668dd`. This checker cannot tell a scanning artifact from a
    fabricated section, so it must not report one as the other.
    """
    verdict = resolve_section(index, "99", "20l")

    assert verdict.form is SectionForm.UNRESOLVED
    assert not verdict.is_defect


def test_a_transferred_section_is_a_defect_though_it_exists(index: UsCodeIndex) -> None:
    """`42 U.S.C. § 14135a` moved to title 34 in 2017 and is still cited as 42.

    A statute leaving the title it was cited under has no case-citation
    equivalent -- the nearest, an overruled case, needs a citator and a
    judgement, while this is recorded as a fact in the Code.
    """
    verdict = resolve_section(index, "99", "6")

    assert verdict.form is SectionForm.SECTION
    assert verdict.not_in_force == (("6", ProvisionStatus.TRANSFERRED),)
    assert verdict.is_defect
