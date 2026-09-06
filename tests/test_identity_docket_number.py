"""The docket number's format as a second witness to the docket's court."""

from __future__ import annotations

import pytest

from mellea_lrc.validation.identity.docket_number import (
    court_level,
    read_docket_number,
    run_docket_number_check,
)
from mellea_lrc.validation.types import (
    DocketCourtRetrievalNode,
    DocketCourtRetrievalOutcome,
    FieldCheckOutcome,
    ValidationNodeStatus,
)


@pytest.mark.parametrize(
    ("number", "levels", "courts", "initials"),
    [
        ("No. CV 93-4868 DT (Ex)", {"trial"}, {"cacd"}, "DT"),
        ("18-CV-4418 (ALC)", {"trial"}, set(), "ALC"),
        ("Case No. 14–cr–00141 (CRC)", {"trial"}, set(), "CRC"),
        ("Civil Action 05-1452 (RBW)", {"trial"}, set(), "RBW"),
        ("Civil Action No. 2014-1005", {"trial"}, set(), None),
        ("Civil Action 09-0033", {"trial"}, set(), None),
        ("Case 08-2027-JWL, 08-2191-JWL", {"trial"}, set(), "JWL"),
        ("5:03-misc-00007", {"trial"}, set(), None),
        ("Civil Action L-07-132", {"trial"}, {"txsd"}, None),
        ("13-2316", {"appellate", "bankruptcy"}, set(), None),
        ("12-4067, 12-4063, 12-4061", {"appellate", "bankruptcy"}, set(), None),
        ("16-10303", {"appellate", "bankruptcy"}, {"ca5", "ca9", "ca11"}, None),
        (
            "Nos. 93-50859, 93-50860, 94-50010, 95-50270 and 50271",
            {"appellate", "bankruptcy"},
            {"ca5", "ca9", "ca11"},
            None,
        ),
        ("15-10602", {"appellate", "bankruptcy"}, {"ca5", "ca9", "ca11"}, None),
        ("15-1987P", {"appellate"}, {"ca1"}, None),
        ("Docket 07-2872-cv", {"appellate"}, {"ca2"}, None),
        ("06-1590-CV", {"appellate"}, {"ca2"}, None),
        ("Docket 09-1074-cr", {"appellate"}, {"ca2"}, None),
        ("2019-1234", {"appellate"}, {"cafc"}, None),
        ("20-10234-bk", {"bankruptcy"}, set(), None),
        ("No. 10 Civ. 07497 (VM)(DF)", {"trial"}, set(), "VM"),
        ("96 Civ. 8414(CBM)", {"trial"}, set(), "CBM"),
        ("Civ. A. No. 89-S-501", {"trial"}, set(), None),
        ("Civ. No. 08-787-LPS", {"trial"}, set(), "LPS"),
        ("CV11-232-PHX-JAT", {"trial"}, set(), "PHX"),
        ("CIV 10-0366 JB/LFG", {"trial"}, set(), None),
        ("CAUSE NO.: 2:17-CV-33-JTM-PRC", {"trial"}, set(), "JTM"),
        ("606, Docket 84-7925", {"appellate", "bankruptcy"}, set(), None),
        ("338, 625, Dockets 85-1226, 85-1228", {"appellate", "bankruptcy"}, set(), None),
        ("Index No. 12345/2013", set(), set(), None),
        ("E2010-00991-SC-R11-CV", set(), set(), None),
        ("02S01-9510-PB-00104", set(), set(), None),
        ("1 CA-CV 93-0218", set(), set(), None),
        ("CV 86-0148-PR", set(), set(), None),
        ("Case No. 13-13098 (REG) (Jointly Administered)", set(), set(), "REG"),
    ],
)
def test_a_number_is_read_for_its_levels_its_courts_and_its_judge(number, levels, courts, initials) -> None:
    reading = read_docket_number(number)
    assert reading is not None
    assert reading.levels == frozenset(levels)
    assert reading.courts == frozenset(courts)
    assert reading.judge_initials == initials


def test_no_number_reads_as_nothing() -> None:
    assert read_docket_number(None) is None
    assert read_docket_number("  ") is None


def test_federal_district_courts_are_trial_courts_whatever_courts_db_types_them() -> None:
    # courts-db types `ilsd`, `ksd` and `dcd` as appellate.
    assert court_level("ilsd") == "trial"
    assert court_level("ksd") == "trial"
    assert court_level("dcd") == "trial"
    assert court_level("cadc") == "appellate"
    assert court_level("ca9") == "appellate"
    assert court_level("cacb") == "bankruptcy"
    assert court_level(None) is None


def _retrieval(number: str | None, court: str | None) -> DocketCourtRetrievalNode:
    return DocketCourtRetrievalNode(
        node_id="c:docket_court_retrieval",
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=DocketCourtRetrievalOutcome.FOUND if court else DocketCourtRetrievalOutcome.UNAVAILABLE,
        docket_id="1",
        court_id=court,
        depends_on=("c",),
        docket_number=number,
    )


def test_a_convention_that_names_another_court_is_a_disagreement() -> None:
    node = run_docket_number_check(_retrieval("No. CV 93-4868 DT (Ex)", "cand"))
    assert node.outcome is FieldCheckOutcome.MISMATCH
    assert node.courts == ("cacd",)
    assert node.evidence == "(Ex)"
    assert "cand" in (node.outcome_message or "")


def test_a_level_that_fits_the_court_agrees() -> None:
    node = run_docket_number_check(_retrieval("13-2316", "ca7"))
    assert node.outcome is FieldCheckOutcome.MATCH
    assert node.levels == ("appellate", "bankruptcy")
    assert run_docket_number_check(_retrieval("16-10303", "mdb")).outcome is FieldCheckOutcome.MATCH


def test_a_district_number_on_a_court_of_appeals_docket_disagrees() -> None:
    node = run_docket_number_check(_retrieval("Case No. 14–cr–00141 (CRC)", "cadc"))
    assert node.outcome is FieldCheckOutcome.MISMATCH
    assert node.judge_initials == "CRC"


def test_a_trial_number_on_a_district_docket_agrees_and_cannot_tell_districts_apart() -> None:
    # S.D.N.Y.'s form under an S.D. Illinois docket: the level fits, and the
    # format alone does not say which district.
    node = run_docket_number_check(_retrieval("18-CV-4418 (ALC)", "ilsd"))
    assert node.outcome is FieldCheckOutcome.MATCH


def test_a_five_digit_circuit_number_under_another_circuit_disagrees() -> None:
    node = run_docket_number_check(_retrieval("97-16383", "ca3"))
    assert node.outcome is FieldCheckOutcome.MISMATCH
    assert node.courts == ("ca11", "ca5", "ca9")


def test_a_number_the_check_cannot_read_is_unavailable() -> None:
    node = run_docket_number_check(_retrieval("Index No. 12345/2013", "nysupct"))
    assert node.status is ValidationNodeStatus.SUCCEEDED
    assert node.outcome is FieldCheckOutcome.UNAVAILABLE


def test_no_number_or_no_court_skips() -> None:
    assert run_docket_number_check(_retrieval(None, "ca7")).status is ValidationNodeStatus.SKIPPED
    assert run_docket_number_check(_retrieval("13-2316", None)).status is ValidationNodeStatus.SKIPPED
