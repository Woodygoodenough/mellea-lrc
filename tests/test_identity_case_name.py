"""Tests for the rule-based case-name comparison and the date comparison."""

from __future__ import annotations

import pytest

from mellea_lrc.core.citations import CitationDate, FullCaseCitation, Reporter
from mellea_lrc.validation.identity.case_name import compare_case_names
from mellea_lrc.validation.identity.field_checks import iso_date, run_court_comparison, run_date_check
from mellea_lrc.validation.identity.reporter_courts import describe, implied_courts
from mellea_lrc.validation.types import (
    CandidateEvaluationNode,
    CandidateEvaluationOutcome,
    CandidateEvaluationSource,
    CaseNameAgreement,
    DatePrecision,
    FieldCheckOutcome,
    ValidationNodeStatus,
)


@pytest.mark.parametrize(
    ("plaintiff", "defendant", "recorded", "expected"),
    [
        ("Ashcroft", "Iqbal", "Ashcroft v. Iqbal", CaseNameAgreement.EXACT),
        ("Ashcroft", "Iqbal", "ashcroft  v. iqbal", CaseNameAgreement.EXACT),
        # A written name shorter than the record's is the ordinary way to cite.
        ("Golden", None, "Bobby Ray Golden", CaseNameAgreement.CONTAINED),
        ("Reyes", "Pac. Bell", "Victor Reyes v. Pacific Bell", CaseNameAgreement.CONTAINED),
        ("Bell Atl. Corp.", "Twombly", "Bell Atlantic Corp. v. Twombly", CaseNameAgreement.CONTAINED),
        ("U.S.", "Smith", "United States v. Smith", CaseNameAgreement.CONTAINED),
        ("Brown", "Board", "Brown v. Board of Education", CaseNameAgreement.CONTAINED),
        ("Dávila-González", None, "United States v. Davila-Gonzalez", CaseNameAgreement.CONTAINED),
        # A plural abbreviation keeps its s past the cut.
        (
            "Hoover",
            "Langston Equip. Assocs., Inc.",
            "Hoover v. Langston Equipment Associates, Inc.",
            CaseNameAgreement.CONTAINED,
        ),
        ("Smith", "Bros. Lumber", "Smith v. Brothers Lumber Co.", CaseNameAgreement.CONTAINED),
        # The record may be the abbreviated side.
        (
            "Monell",
            "Department of Social Services",
            "Monell v. New York City Dept. of Social Servs.",
            CaseNameAgreement.CONTAINED,
        ),
        (
            "Doe",
            "Commonwealth's Attorney",
            "Doe v. Commonwealth's Atty. for City of Richmond",
            CaseNameAgreement.CONTAINED,
        ),
        # Apostrophe contractions, and words a filing runs together.
        (
            "Pioneer Inv. Servs. Co.",
            "Brunswick Assocs. Ltd. P'ship",
            "Pioneer Investment Services Co. v. Brunswick Associates Ltd. Partnership",
            CaseNameAgreement.CONTAINED,
        ),
        (
            "Hausler",
            "JPMorgan Chase Bank, N.A.",
            "Hausler v. JP Morgan Chase Bank, N.A.",
            CaseNameAgreement.CONTAINED,
        ),
        (
            "United States",
            "MoralesQuinones",
            "United States v. Miguel Morales-Quinones",
            CaseNameAgreement.CONTAINED,
        ),
        # An acronym the filing set in capitals is the record's initials.
        (
            "CFTC",
            "American Metals Exchange",
            "Commodity Futures Trading Commission v. American Metals Exchange Corp.",
            CaseNameAgreement.CONTAINED,
        ),
        (
            "Karim-Panahi",
            "LAPD",
            "Karim-Panahi v. Los Angeles Police Department",
            CaseNameAgreement.CONTAINED,
        ),
        (
            "Packard Elevator",
            "ICC",
            "Packard Elevator v. Interstate Commerce Commission",
            CaseNameAgreement.CONTAINED,
        ),
        ("Smith", "ABC", "Smith v. Acme Brick Co.", CaseNameAgreement.CONTAINED),
        ("Smith", "XYZ", "Smith v. Acme Brick Co.", CaseNameAgreement.MISMATCH),
        # The record may stop short of the acronym's last word.
        ("FDIC", "Garner", "Federal Deposit Insurance v. Garner", CaseNameAgreement.CONTAINED),
        ("Smith", "ABCD", "Smith v. A", CaseNameAgreement.MISMATCH),
        # Contractions with the apostrophe removed.
        (
            "George",
            "Prof'l Disposables Int'l, Inc.",
            "George v. Professional Disposables International, Inc.",
            CaseNameAgreement.CONTAINED,
        ),
        (
            "Lujan",
            "Nat'l Wildlife Fed'n",
            "Lujan v. National Wildlife Federation",
            CaseNameAgreement.CONTAINED,
        ),
        (
            "Alaska",
            "Native Village of Venetie Tribal Gov't",
            "Alaska v. Native Village of Venetie Tribal Government",
            CaseNameAgreement.CONTAINED,
        ),
        # Either side may be the fuller one: the archive truncates a caption too.
        (
            "Planned Parenthood Minn., N.D., S.D.",
            "Rounds",
            "Planned Parenthood, etc. v. Mike Rounds",
            CaseNameAgreement.CONTAINED,
        ),
        ("Brown", "Board of Education", "Brown v. Board", CaseNameAgreement.CONTAINED),
        # A misspelling is left to the judgement, which says whether it is one.
        (
            "Rufo",
            "Inmates of Suffock County Jail",
            "Rufo v. Inmates of Suffolk County Jail",
            CaseNameAgreement.MISMATCH,
        ),
        # Sides swap on a cross-appeal.
        ("Iqbal", "Ashcroft", "Ashcroft v. Iqbal", CaseNameAgreement.CONTAINED),
        # A single-party caption on either side.
        (None, "Golden", "In re Golden", CaseNameAgreement.CONTAINED),
        ("Smith", "Jones", "Smith vs. Jones-Bar Corp.", CaseNameAgreement.CONTAINED),
        # A different party on one side is a different case.
        ("Smith", "Jones", "Smith v. Williams", CaseNameAgreement.MISMATCH),
        ("Conley", "Gibson", "Galeana v. Galeana", CaseNameAgreement.MISMATCH),
        # A two-party name against a one-party record is not contained in it.
        ("Golden", "Silver", "In re Golden", CaseNameAgreement.MISMATCH),
        # Absence decides nothing.
        ("Brown", "Board", None, CaseNameAgreement.UNAVAILABLE),
        (None, None, "Brown v. Board", CaseNameAgreement.UNAVAILABLE),
        ("The", "Inc.", "Brown v. Board", CaseNameAgreement.UNAVAILABLE),
        ("Schwartz", "American College", "No. 98-2228", CaseNameAgreement.UNAVAILABLE),
    ],
)
def test_compare_case_names(
    plaintiff: str | None, defendant: str | None, recorded: str | None, expected: CaseNameAgreement
) -> None:
    comparison = compare_case_names(plaintiff=plaintiff, defendant=defendant, recorded=recorded)
    assert comparison.agreement is expected
    assert comparison.agreement.agrees is (expected in (CaseNameAgreement.EXACT, CaseNameAgreement.CONTAINED))
    assert comparison.reason


@pytest.mark.parametrize(
    ("date", "expected"),
    [
        (None, None),
        (CitationDate(year="2007"), "2007"),
        (CitationDate(year="2024", month="Oct.", day="31"), "2024-10-31"),
        (CitationDate(year="2024", month="Sept.", day="3"), "2024-09-03"),
        (CitationDate(year="2024", month="Nonsense", day="3"), "2024"),
    ],
)
def test_iso_date(date: CitationDate | None, expected: str | None) -> None:
    assert iso_date(date) == expected


def _candidate(date_filed: str | None) -> CandidateEvaluationNode:
    return CandidateEvaluationNode(
        node_id="c1:locator_candidate_evaluation:1",
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=CandidateEvaluationOutcome.READY,
        source=CandidateEvaluationSource.LOCATOR_LOOKUP,
        candidate_index=1,
        cluster_id="x",
        case_name=None,
        date_filed=date_filed,
        court_id=None,
        docket_id=None,
        record={},
        depends_on=(),
    )


@pytest.mark.parametrize(
    ("stated", "filed", "outcome", "precision"),
    [
        (CitationDate(year="2007"), "2007-05-21", FieldCheckOutcome.MATCH, DatePrecision.YEAR),
        (CitationDate(year="2008"), "2007-05-21", FieldCheckOutcome.MISMATCH, DatePrecision.YEAR),
        (
            CitationDate(year="2024", month="Oct.", day="31"),
            "2024-10-31",
            FieldCheckOutcome.MATCH,
            DatePrecision.DAY,
        ),
        (
            CitationDate(year="2024", month="Oct.", day="30"),
            "2024-10-31",
            FieldCheckOutcome.MISMATCH,
            DatePrecision.DAY,
        ),
        (None, "2007-05-21", FieldCheckOutcome.UNAVAILABLE, None),
        (CitationDate(year="2007"), None, FieldCheckOutcome.UNAVAILABLE, None),
    ],
)
def test_the_date_is_compared_at_the_precision_the_filing_stated(
    stated: CitationDate | None,
    filed: str | None,
    outcome: FieldCheckOutcome,
    precision: DatePrecision | None,
) -> None:
    node = run_date_check(FullCaseCitation(date=stated), candidate=_candidate(filed))
    assert node.outcome is outcome
    assert node.precision is precision
    assert node.depends_on == ("c1:locator_candidate_evaluation:1",)


def _reporter(name: str, *, scotus: bool = False) -> Reporter:
    return Reporter(as_written=name, short_name=name, editions=(name,), is_scotus=scotus)


@pytest.mark.parametrize(
    ("reporter", "inside", "outside"),
    [
        ("N.C. App.", ("ncctapp", "nc"), ("txsd", "ca4")),
        ("N.C.", ("nc", "ncctapp"), ("txsd",)),
        ("So. 3d", ("fladistctapp", "fla", "lactapp"), ("ca9", "nysd")),
        ("A.D.3d", ("nyappdiv", "ny"), ("ca2",)),
        ("Cal. App. 5th", ("calctapp",), ("cal", "cacd")),
        ("F. App'x", ("ca4", "cadc", "cafc"), ("nysd", "fladistctapp")),
        ("B.R.", ("nysb", "bap9"), ("fladistctapp",)),
        # An identifier courts-db did not build regularly is found by place.
        ("F. Supp. 2d", ("nmid", "nysd", "gud"), ("fladistctapp", "nc")),
    ],
)
def test_a_reporter_implies_a_family_of_courts(
    reporter: str, inside: tuple[str, ...], outside: tuple[str, ...]
) -> None:
    family = implied_courts(_reporter(reporter))
    assert all(court in family for court in inside), sorted(family)[:10]
    assert not any(court in family for court in outside)


def test_the_supreme_court_reporter_implies_the_supreme_court() -> None:
    assert "scotus" in implied_courts(_reporter("U.S.", scotus=True))
    assert implied_courts(None) == frozenset()
    assert implied_courts(Reporter(as_written="Nowhere")) == frozenset()
    assert describe(frozenset({"b", "a"})) == "a, b"
    assert describe(frozenset(f"c{i}" for i in range(10))).endswith("(10 courts)")


def _court_candidate(court_id: str | None) -> CandidateEvaluationNode:
    return CandidateEvaluationNode(
        node_id="c1:locator_candidate_evaluation:1",
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=CandidateEvaluationOutcome.READY,
        source=CandidateEvaluationSource.LOCATOR_LOOKUP,
        candidate_index=1,
        cluster_id="x",
        case_name=None,
        date_filed=None,
        court_id=court_id,
        docket_id=None,
        record={},
        depends_on=(),
    )


def test_an_unstated_court_is_compatible_or_in_conflict_with_the_reporter() -> None:
    citation = FullCaseCitation(reporter=_reporter("N.C. App."), court=None)
    compatible = run_court_comparison(citation, evidence=_court_candidate("ncctapp"))
    assert compatible.outcome is FieldCheckOutcome.COMPATIBLE
    assert "ncctapp" in compatible.implied_court_ids
    conflict = run_court_comparison(citation, evidence=_court_candidate("txsd"))
    assert conflict.outcome is FieldCheckOutcome.MISMATCH
    assert "not one the reporter holds" in (conflict.outcome_message or "")
    unknown = run_court_comparison(
        FullCaseCitation(reporter=Reporter(as_written="Nowhere")), evidence=_court_candidate("txsd")
    )
    assert unknown.outcome is FieldCheckOutcome.UNAVAILABLE
    stated = run_court_comparison(
        FullCaseCitation(reporter=_reporter("N.C. App."), court="nc"), evidence=_court_candidate("ncctapp")
    )
    assert stated.outcome is FieldCheckOutcome.MISMATCH
    assert stated.implied_court_ids == ()
