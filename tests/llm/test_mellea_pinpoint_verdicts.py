"""Live evaluations for the pinpoint check's three page-level verdicts.

The interesting behaviour is the boundary between `absent_from_page` and
`inconclusive`. A page on the proposition's subject that does not carry it is
an absence; a page about something else entirely is not a finding at all, and
reporting it as one would assert a defect the evidence does not establish.
"""

from __future__ import annotations

import asyncio

import pytest
from dotenv import load_dotenv

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.core.spans import Span
from mellea_lrc.extraction import ExtractedCitation
from mellea_lrc.validation import (
    CitationValidation,
    EvidenceQuoteMatchMethod,
    MelleaCitingPropositionExtractionNode,
    MelleaCitingPropositionExtractionOutcome,
    MelleaPinpointCheckOutcome,
    ReporterPageEvidence,
    ReporterPageRetrievalNode,
    ReporterPageRetrievalOutcome,
    ValidationNodeStatus,
)
from mellea_lrc.validation.pinpoint_retrieval import run_mellea_pinpoint_check

load_dotenv(".env")

# One page of a hypothetical opinion about equal protection in school
# assignment, written so that it carries one proposition and plainly does not
# carry a second on the same subject.
ON_SUBJECT_PAGE = (
    "We come then to the question presented: does segregation of children in public "
    "schools solely on the basis of race deprive the children of the minority group of "
    "equal educational opportunities? We believe that it does. Separate educational "
    "facilities are inherently unequal. Such segregation is a denial of the equal "
    "protection of the laws. Our decision therefore rests on the effect of segregation "
    "itself upon public education, and we need not consider the tangible factors the "
    "District has catalogued at length."
)

OFF_SUBJECT_PAGE = (
    "The vessel was chartered under a time charter providing for redelivery at a port "
    "in the Baltic range. Demurrage accrued from the expiry of laytime, and the "
    "charterer's obligation to pay it is independent of any claim for detention. The "
    "arbitrators found the delay attributable to congestion at the discharge berth."
)


def _retrieval(page_text: str) -> ReporterPageRetrievalNode:
    return ReporterPageRetrievalNode(
        node_id="live-pinpoint:reporter_page",
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=ReporterPageRetrievalOutcome.FOUND,
        cluster_id="1",
        reporter_citation="347 U.S. 483",
        pin_cite="495",
        citation_index=1,
        evidence=ReporterPageEvidence(
            opinion_id="1",
            opinion_type="020lead",
            text=page_text,
        ),
        depends_on=(),
    )


def _proposition(
    retrieval: ReporterPageRetrievalNode, proposition: str
) -> MelleaCitingPropositionExtractionNode:
    citing_document = f"The District's plan cannot stand. {proposition} See 347 U.S. 483, 495."
    start = citing_document.index(proposition)
    return MelleaCitingPropositionExtractionNode(
        node_id=f"{retrieval.node_id}:mellea_citing_proposition_extraction",
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=MelleaCitingPropositionExtractionOutcome.IDENTIFIED,
        context_span=Span(0, len(citing_document)),
        reasoning="The sentence immediately attributes this proposition to the citation.",
        proposition=proposition,
        proposition_span=Span(start, start + len(proposition)),
        proposition_match_method=EvidenceQuoteMatchMethod.EXACT,
        proposition_match_score=1.0,
        depends_on=(retrieval.node_id,),
    )


@pytest.mark.llm_evaluation
@pytest.mark.parametrize(
    ("page", "proposition", "expected"),
    [
        (
            ON_SUBJECT_PAGE,
            "Segregating public school children by race denies them equal educational opportunity.",
            MelleaPinpointCheckOutcome.SUPPORTS,
        ),
        (
            # The remedial holding of the same litigation, decided on a page
            # this one is not. Squarely the page's own subject, and squarely
            # not on it -- which is what a wrong pinpoint looks like.
            ON_SUBJECT_PAGE,
            "School desegregation must proceed with all deliberate speed.",
            MelleaPinpointCheckOutcome.ABSENT_FROM_PAGE,
        ),
        (
            OFF_SUBJECT_PAGE,
            "Segregating public school children by race denies them equal educational opportunity.",
            MelleaPinpointCheckOutcome.INCONCLUSIVE,
        ),
    ],
)
def test_pinpoint_check_separates_absence_from_inability_to_judge(
    page: str,
    proposition: str,
    expected: MelleaPinpointCheckOutcome,
) -> None:
    """An on-subject page yields a finding; an off-subject page yields none."""
    retrieval = _retrieval(page)
    proposition_node = _proposition(retrieval, proposition)
    citation = ExtractedCitation(
        citation_id="live-pinpoint",
        matched_text="347 U.S. 483, 495",
        citation=FullCaseCitation(
            volume="347",
            reporter="U.S.",
            page="483",
            pin_cite="495",
        ),
        span=Span(start=0, end=17),
        locator_span=Span(start=0, end=12),
    )

    node = asyncio.run(
        run_mellea_pinpoint_check(
            CitationValidation(citation=citation).append(retrieval).append(proposition_node),
            retrieval=retrieval,
            proposition=proposition_node,
        )
    )

    assert node.status is ValidationNodeStatus.SUCCEEDED
    assert node.outcome is expected
    if expected is MelleaPinpointCheckOutcome.INCONCLUSIVE:
        return
    assert node.evidence_quote is not None
    assert node.evidence_span is not None
    assert page[node.evidence_span.start : node.evidence_span.end] == node.evidence_quote
