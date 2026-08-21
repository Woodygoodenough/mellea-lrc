"""Tests for the quotation check as a validation node."""

from __future__ import annotations

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.core.spans import Span
from mellea_lrc.extraction import ExtractedCitation
from mellea_lrc.validation.quotation import run_quotation_check
from mellea_lrc.validation.types import (
    CitationValidation,
    QuotationCheckOutcome,
    ReporterPageEvidence,
    ReporterPageRetrievalNode,
    ReporterPageRetrievalOutcome,
    ValidationNodeStatus,
)

PAGE = (
    "To survive a motion to dismiss, a complaint must contain sufficient factual matter, "
    "accepted as true, to state a claim to relief that is plausible on its face."
)


def _retrieval(*, found: bool = True) -> ReporterPageRetrievalNode:
    return ReporterPageRetrievalNode(
        node_id="cite-0001:reporter_page_retrieval",
        status=ValidationNodeStatus.SUCCEEDED if found else ValidationNodeStatus.SKIPPED,
        outcome=ReporterPageRetrievalOutcome.FOUND if found else ReporterPageRetrievalOutcome.UNAVAILABLE,
        cluster_id="1",
        reporter_citation="550 U.S. 544",
        pin_cite="570",
        citation_index=1,
        evidence=ReporterPageEvidence(opinion_id="2", opinion_type="020lead", text=PAGE) if found else None,
        depends_on=(),
    )


def _validation(document_text: str, citation_span: Span) -> CitationValidation:
    return CitationValidation(
        citation=ExtractedCitation(
            citation_id="cite-0001",
            span=citation_span,
            locator_span=citation_span,
            matched_text="550 U.S. 544",
            citation=FullCaseCitation(volume="550", reporter="U.S.", page="544", pin_cite="570"),
        )
    )


def test_an_altered_quotation_is_reported_with_the_words_that_differ() -> None:
    """The node carries the substitution, not merely a verdict."""
    citing = (
        'The Court held a complaint must "contain sufficient factual detail, accepted as true, '
        'to state a claim to relief that is plausible on its face." 550 U.S. 544, 570.'
    )
    span = Span(citing.index("550 U.S. 544"), len(citing))

    node = run_quotation_check(_validation(citing, span), retrieval=_retrieval(), document_text=citing)

    assert node.status is ValidationNodeStatus.SUCCEEDED
    assert node.outcome is QuotationCheckOutcome.ALTERED
    (passage,) = node.passages
    assert ("detail", "matter") in passage.substitutions


def test_quoted_spans_index_the_document_not_the_window() -> None:
    """A span that indexed the extraction window would not locate anything."""
    prefix = "Background paragraph. " * 40
    citing = (
        f"{prefix}The Court held a complaint must "
        '"contain sufficient factual matter, accepted as true, to state a claim to relief '
        'that is plausible on its face." 550 U.S. 544, 570.'
    )
    span = Span(citing.index("550 U.S. 544"), len(citing))

    node = run_quotation_check(_validation(citing, span), retrieval=_retrieval(), document_text=citing)

    (passage,) = node.passages
    assert citing[passage.quoted_span.start : passage.quoted_span.end] == passage.quoted_text


def test_a_faithful_quotation_leaves_the_node_verbatim() -> None:
    """Nothing is asserted about a citation whose quotations check out."""
    citing = (
        'The Court held a complaint must "contain sufficient factual matter, accepted as true, '
        'to state a claim to relief that is plausible on its face." 550 U.S. 544, 570.'
    )
    span = Span(citing.index("550 U.S. 544"), len(citing))

    node = run_quotation_check(_validation(citing, span), retrieval=_retrieval(), document_text=citing)

    assert node.outcome is QuotationCheckOutcome.VERBATIM


def test_citing_text_without_quotations_is_not_a_finding() -> None:
    """Most citations quote nothing, and that is not a defect."""
    citing = "The pleading standard is settled. 550 U.S. 544, 570."
    span = Span(citing.index("550 U.S. 544"), len(citing))

    node = run_quotation_check(_validation(citing, span), retrieval=_retrieval(), document_text=citing)

    assert node.outcome is QuotationCheckOutcome.NO_QUOTATIONS


def test_no_retrieved_page_skips_rather_than_concludes() -> None:
    """Without the page there is nothing to check the quotation against."""
    citing = 'It said a complaint must "state a claim to relief." 550 U.S. 544, 570.'
    span = Span(citing.index("550 U.S. 544"), len(citing))

    node = run_quotation_check(
        _validation(citing, span), retrieval=_retrieval(found=False), document_text=citing
    )

    assert node.status is ValidationNodeStatus.SKIPPED
    assert node.outcome is QuotationCheckOutcome.UNAVAILABLE
    assert node.passages == ()


def test_one_altered_quotation_decides_the_node() -> None:
    """A faithful quotation elsewhere does not excuse an altered one."""
    citing = (
        'The Court said a complaint must "contain sufficient factual matter, accepted as true" '
        'and also that it must "state a claim to entitlement that is plausible on its face." '
        "550 U.S. 544, 570."
    )
    span = Span(citing.index("550 U.S. 544"), len(citing))

    node = run_quotation_check(_validation(citing, span), retrieval=_retrieval(), document_text=citing)

    assert node.outcome is QuotationCheckOutcome.ALTERED
    assert len(node.passages) == 2
