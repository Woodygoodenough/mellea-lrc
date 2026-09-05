"""Tests for the rule-based case-name comparison and the date comparison."""

from __future__ import annotations

import pytest

from mellea_lrc.core.citations import CitationDate, FullCaseCitation
from mellea_lrc.validation.identity.case_name import compare_case_names
from mellea_lrc.validation.identity.field_checks import iso_date, run_date_check
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
        # A misspelling is left to the judgement, which can call it a variant.
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
