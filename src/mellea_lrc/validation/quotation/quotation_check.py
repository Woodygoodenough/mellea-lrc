"""Check every quotation the citing text attributes to a retrieved reporter page."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mellea_lrc.core.spans import Span
from mellea_lrc.validation.pinpoint_retrieval.mellea_citing_proposition_extraction import (
    citing_context_span,
)
from mellea_lrc.validation.quotation.verbatim import QuotationOutcome, check_quotations
from mellea_lrc.validation.types import (
    QuotationCheckNode,
    QuotationCheckOutcome,
    QuotedPassageEvidence,
    ReporterPageRetrievalNode,
    ReporterPageRetrievalOutcome,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from mellea_lrc.validation.quotation.verbatim import QuotationFinding
    from mellea_lrc.validation.types import CitationValidation

# Worst finding first: one altered quotation is the citation's verdict even when
# every other quotation on the page is faithful.
_PRECEDENCE = (
    QuotationOutcome.ALTERED,
    QuotationOutcome.NOT_ON_PAGE,
    QuotationOutcome.VERBATIM,
    QuotationOutcome.UNCHECKABLE,
)
_NODE_OUTCOME = {
    QuotationOutcome.ALTERED: QuotationCheckOutcome.ALTERED,
    QuotationOutcome.NOT_ON_PAGE: QuotationCheckOutcome.NOT_ON_PAGE,
    QuotationOutcome.VERBATIM: QuotationCheckOutcome.VERBATIM,
    QuotationOutcome.UNCHECKABLE: QuotationCheckOutcome.NO_QUOTATIONS,
}
_OUTCOME_MESSAGES = {
    QuotationCheckOutcome.VERBATIM: "Every quotation checked appears on the cited page as written.",
    QuotationCheckOutcome.ALTERED: "A quotation differs from the words on the cited page.",
    QuotationCheckOutcome.NOT_ON_PAGE: "A quotation does not appear on the cited page.",
    QuotationCheckOutcome.NO_QUOTATIONS: "The citing text states no quotation this page can settle.",
}


def run_quotation_check(
    validation: CitationValidation,
    *,
    retrieval: ReporterPageRetrievalNode,
    document_text: str,
) -> QuotationCheckNode:
    """Check the citing text's quotations against the page the citation names.

    Deterministic: no model is involved. The window is the same one the
    proposition extraction reads, so the two nodes speak about the same passage
    of the filing.
    """
    evidence = retrieval.evidence
    if retrieval.outcome is not ReporterPageRetrievalOutcome.FOUND or evidence is None:
        return _node(
            retrieval,
            ValidationNodeStatus.SKIPPED,
            QuotationCheckOutcome.UNAVAILABLE,
            context_span=None,
            passages=(),
            status_message="Skipped the quotation check because no reporter page was retrieved.",
            outcome_message="A retrieved reporter page is required.",
        )

    context_span = citing_context_span(document_text, validation.citation.span)
    citing_context = document_text[context_span.start : context_span.end]
    try:
        findings = check_quotations(evidence.text, citing_context)
    except Exception as exc:
        return _node(
            retrieval,
            ValidationNodeStatus.FAILED,
            QuotationCheckOutcome.FAILED,
            context_span=context_span,
            passages=(),
            status_message="The quotation check failed during execution.",
            outcome_message="No quotation finding is available.",
            error=f"{type(exc).__name__}: {exc}",
        )

    if not findings:
        return _node(
            retrieval,
            ValidationNodeStatus.SUCCEEDED,
            QuotationCheckOutcome.NO_QUOTATIONS,
            context_span=context_span,
            passages=(),
            status_message="The quotation check completed.",
            outcome_message=_OUTCOME_MESSAGES[QuotationCheckOutcome.NO_QUOTATIONS],
        )

    outcome = _NODE_OUTCOME[
        next(candidate for candidate in _PRECEDENCE if any(f.outcome is candidate for f in findings))
    ]
    return _node(
        retrieval,
        ValidationNodeStatus.SUCCEEDED,
        outcome,
        context_span=context_span,
        passages=tuple(_evidence(finding, context_span) for finding in findings),
        status_message="The quotation check completed.",
        outcome_message=_OUTCOME_MESSAGES[outcome],
    )


def _evidence(finding: QuotationFinding, context_span: Span) -> QuotedPassageEvidence:
    """Re-base the quoted span onto the document, so spans stay document offsets."""
    return QuotedPassageEvidence(
        quoted_text=finding.quoted_text,
        quoted_span=Span(
            context_span.start + finding.quoted_span.start,
            context_span.start + finding.quoted_span.end,
        ),
        outcome=finding.outcome.value,
        score=finding.score,
        page_span=finding.page_span,
        page_text=finding.page_text,
        substitutions=tuple(pair for pair in finding.differences if pair[0] != pair[1]),
    )


def _node(
    retrieval: ReporterPageRetrievalNode,
    status: ValidationNodeStatus,
    outcome: QuotationCheckOutcome,
    *,
    context_span: Span | None,
    passages: tuple[QuotedPassageEvidence, ...],
    status_message: str | None = None,
    outcome_message: str | None = None,
    error: str | None = None,
) -> QuotationCheckNode:
    return QuotationCheckNode(
        node_id=f"{retrieval.node_id}:quotation_check",
        status=status,
        outcome=outcome,
        context_span=context_span,
        passages=passages,
        depends_on=(retrieval.node_id,),
        status_message=status_message,
        outcome_message=outcome_message,
        error=error,
    )
