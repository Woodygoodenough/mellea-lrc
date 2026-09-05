"""The rule-based guard: three comparisons that cost no model call.

Each reads the record's *current* citation -- the filing's reading as corrected
so far -- rather than the extracted one, and each answers ``UNAVAILABLE`` from
an absence rather than guessing. A disagreement here is not a finding. It is
what sends the citation to the composite judgement, which sees the filing's
context instead of two fields.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.validation.identity.case_name import CaseNameAgreement, compare_case_names
from mellea_lrc.validation.identity.reporter_courts import describe, implied_courts
from mellea_lrc.validation.types import (
    CaseNameAgreementNode,
    CourtCheckNode,
    DateCheckNode,
    DatePrecision,
    FieldCheckOutcome,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from mellea_lrc.core.citations import CanonicalCitation, CitationDate
    from mellea_lrc.validation.types import CandidateEvaluationNode, DocketCourtRetrievalNode

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip


def iso_date(date: CitationDate | None) -> str | None:
    """The date a citation states as ``YYYY`` or ``YYYY-MM-DD``, or None."""
    if date is None:
        return None
    if not date.is_exact:
        return date.year
    month = _MONTHS.get((date.month or "").rstrip(".").lower()[:4]) or _MONTHS.get(
        (date.month or "").rstrip(".").lower()[:3]
    )
    if month is None or not (date.day or "").isdigit():
        return date.year
    return f"{date.year}-{month:02d}-{int(date.day):02d}"


def run_date_check(citation: CanonicalCitation, *, candidate: CandidateEvaluationNode) -> DateCheckNode:
    """Compare the date the filing states with the record's, at the precision stated.

    A filing writing ``(2007)`` is compared by year, and one writing
    ``(D. Ariz. Oct. 31, 2024)`` by day. The second is what tells apart the
    unpublished decisions a year alone cannot.
    """
    node_id = f"{candidate.node_id}:date_check"
    date = citation.date if isinstance(citation, FullCaseCitation) else None
    extracted = iso_date(date)
    retrieved = candidate.date_filed
    if extracted is None or retrieved is None:
        return DateCheckNode(
            node_id=node_id,
            status=ValidationNodeStatus.SKIPPED,
            outcome=FieldCheckOutcome.UNAVAILABLE,
            precision=None,
            extracted_date=extracted,
            retrieved_date=retrieved,
            depends_on=(candidate.node_id,),
            status_message="Skipped date comparison because one side states no date.",
            outcome_message="Date comparison is unavailable because one date is missing.",
        )
    precision = DatePrecision.DAY if len(extracted) > len("YYYY") else DatePrecision.YEAR
    agree = extracted == retrieved if precision is DatePrecision.DAY else extracted == retrieved[:4]
    return DateCheckNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=FieldCheckOutcome.MATCH if agree else FieldCheckOutcome.MISMATCH,
        precision=precision,
        extracted_date=extracted,
        retrieved_date=retrieved,
        depends_on=(candidate.node_id,),
        status_message="Date comparison completed.",
        outcome_message=(
            f"The filing's date agrees with the record's to the {precision.value}."
            if agree
            else f"The filing's date differs from the record's at the {precision.value}."
        ),
    )


def run_case_name_agreement(
    citation: CanonicalCitation, *, candidate: CandidateEvaluationNode
) -> CaseNameAgreementNode:
    """Compare the parties the filing wrote with the record's case name, by rule."""
    node_id = f"{candidate.node_id}:case_name_agreement"
    if not isinstance(citation, FullCaseCitation):
        comparison = compare_case_names(plaintiff=None, defendant=None, recorded=candidate.case_name)
    else:
        comparison = compare_case_names(
            plaintiff=citation.plaintiff, defendant=citation.defendant, recorded=candidate.case_name
        )
    unavailable = comparison.agreement is CaseNameAgreement.UNAVAILABLE
    return CaseNameAgreementNode(
        node_id=node_id,
        status=ValidationNodeStatus.SKIPPED if unavailable else ValidationNodeStatus.SUCCEEDED,
        outcome=comparison.agreement,
        written_case_name=comparison.written,
        recorded_case_name=comparison.recorded,
        depends_on=(candidate.node_id,),
        status_message=(
            "Skipped case-name comparison because one name is missing."
            if unavailable
            else "Case-name comparison completed."
        ),
        outcome_message=comparison.reason,
    )


def run_court_comparison(
    citation: CanonicalCitation, *, evidence: CandidateEvaluationNode | DocketCourtRetrievalNode
) -> CourtCheckNode:
    """Compare the court the filing states with the one the record's docket names."""
    extracted = citation.court if isinstance(citation, FullCaseCitation) else None
    retrieved = evidence.court_id
    node_id = f"{evidence.node_id}:court_check"
    if extracted is None and retrieved is not None:
        # The filing states no court, but its reporter holds only some courts.
        # A record from one of them is compatible; from any other, a conflict.
        family = implied_courts(citation.reporter if isinstance(citation, FullCaseCitation) else None)
        if family:
            compatible = retrieved in family
            return CourtCheckNode(
                node_id=node_id,
                status=ValidationNodeStatus.SUCCEEDED,
                outcome=FieldCheckOutcome.COMPATIBLE if compatible else FieldCheckOutcome.MISMATCH,
                extracted_court_id=None,
                retrieved_court_id=retrieved,
                depends_on=(evidence.node_id,),
                status_message="Court comparison completed against the courts the reporter holds.",
                outcome_message=(
                    f"The filing states no court; the record's {retrieved} is one the reporter holds."
                    if compatible
                    else (
                        f"The filing states no court, and the record's {retrieved} is not one the "
                        f"reporter holds ({describe(family)})."
                    )
                ),
                implied_court_ids=tuple(sorted(family)),
            )
    if extracted is None or retrieved is None:
        return CourtCheckNode(
            node_id=node_id,
            status=ValidationNodeStatus.SKIPPED,
            outcome=FieldCheckOutcome.UNAVAILABLE,
            extracted_court_id=extracted,
            retrieved_court_id=retrieved,
            depends_on=(evidence.node_id,),
            status_message="Skipped court comparison because one side names no court.",
            outcome_message="Court comparison is unavailable because one court identifier is missing.",
        )
    agree = extracted == retrieved
    return CourtCheckNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=FieldCheckOutcome.MATCH if agree else FieldCheckOutcome.MISMATCH,
        extracted_court_id=extracted,
        retrieved_court_id=retrieved,
        depends_on=(evidence.node_id,),
        status_message="Court comparison completed.",
        outcome_message=(
            "The filing's court agrees with the record's."
            if agree
            else "The filing's court differs from the record's."
        ),
    )
