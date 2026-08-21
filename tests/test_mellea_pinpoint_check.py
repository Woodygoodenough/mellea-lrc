"""Tests for grounded Mellea pinpoint inference."""

import asyncio
from types import SimpleNamespace

import pytest

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.core.spans import Span
from mellea_lrc.extraction import ExtractedCitation
from mellea_lrc.validation.pinpoint_retrieval import mellea_pinpoint_check
from mellea_lrc.validation.pinpoint_retrieval.evidence_quote import resolve_evidence_quote
from mellea_lrc.validation.pinpoint_retrieval.mellea_pinpoint_check import (
    run_mellea_pinpoint_check,
)
from mellea_lrc.validation.types import (
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


def test_absence_from_the_page_is_a_verdict_and_requires_a_quote() -> None:
    """A retrieved page can establish that it does not carry the proposition.

    The claim is about the page, not the citation. It still has to be grounded:
    the quote shows the page was read and is on the proposition's subject, which
    is what separates an absence from a failure to judge.
    """
    page = "The statute bars retroactive application to pending claims."

    proposal = mellea_pinpoint_check._parse(  # noqa: SLF001
        '{"verdict":"absent_from_page","reasoning":"The page addresses retroactivity, not tolling.",'
        '"evidence_quote":"The statute bars retroactive application"}'
    )

    assert proposal.verdict == "absent_from_page"
    assert resolve_evidence_quote(page, proposal.evidence_quote) is not None


def test_an_absence_without_a_quote_is_rejected_for_repair() -> None:
    """An ungrounded absence asserts a defect nothing demonstrates."""
    ctx = SimpleNamespace(
        last_output=lambda: SimpleNamespace(
            value=('{"verdict":"absent_from_page","reasoning":"Not on the page.","evidence_quote":null}')
        )
    )

    result = mellea_pinpoint_check._validate_grounding(ctx, "Some page text.")  # noqa: SLF001

    assert not bool(result)
    assert "absent_from_page" in str(result.reason)


def test_negative_pinpoint_verdict_is_not_part_of_the_model_contract() -> None:
    """No verdict asserts that the cited authority fails to support the proposition.

    `absent_from_page` reports what one page does not carry. A verdict about the
    citation as a whole would need pages this operation never retrieved, so the
    schema still refuses one.
    """
    with pytest.raises(ValueError, match="Invalid Mellea pinpoint output"):
        mellea_pinpoint_check._parse(  # noqa: SLF001
            '{"verdict":"does_not_support","reasoning":"This page does not state the proposition.",'
            '"evidence_quote":null}'
        )

    proposal = mellea_pinpoint_check._parse(  # noqa: SLF001
        '{"verdict":"inconclusive","reasoning":"This page does not permit a reliable judgment.",'
        '"evidence_quote":null}'
    )

    assert proposal.verdict == "inconclusive"
    assert proposal.evidence_quote is None


def test_evidence_quote_resolution_accepts_surface_variation() -> None:
    """Case, Unicode punctuation, and spacing do not prevent exact grounding."""
    source = "The Court’s holding—properly stated—is controlling."

    resolved = resolve_evidence_quote(
        source,
        "the court's  holding-properly stated-is controlling.",
    )

    assert resolved is not None
    assert resolved.method is EvidenceQuoteMatchMethod.NORMALIZED
    assert resolved.text == source
    assert source[resolved.span.start : resolved.span.end] == source


def test_evidence_quote_resolution_allows_one_minor_word_drift() -> None:
    """A long, unique quote tolerates one changed word without trusting offsets."""
    source = "The court concludes that actual knowledge cannot replace proper service in this action."

    resolved = resolve_evidence_quote(
        source,
        "The court concludes that actual notice cannot replace proper service in this action.",
    )

    assert resolved is not None
    assert resolved.method is EvidenceQuoteMatchMethod.FUZZY
    assert resolved.score >= 0.9
    assert resolved.text == source


def test_evidence_quote_resolution_uses_first_ambiguous_match() -> None:
    """The temporary fuzzy policy selects the first repeated passage."""
    sentence = "The court grants the motion for a protective order."
    source = f"{sentence} Background. {sentence}"

    resolved = resolve_evidence_quote(source, sentence)

    assert resolved is not None
    assert resolved.method is EvidenceQuoteMatchMethod.FUZZY
    assert resolved.span == Span(0, len(sentence))


def test_evidence_quote_resolution_ignores_overlapping_shifted_windows() -> None:
    """A nearby shifted window does not defeat an otherwise perfect token match."""
    source = (
        "To survive a motion to dismiss, a complaint must contain sufficient "
        "factual matter, accepted as true, to “state a claim to relief that is "
        "plausible on its face.” Id., at 570."
    )
    proposed = (
        "To survive a motion to dismiss, a complaint must contain sufficient "
        "factual matter, accepted as true, to 'state a claim to relief that is "
        "plausible on its face.'"
    )

    resolved = resolve_evidence_quote(source, proposed)

    assert resolved is not None
    assert resolved.method is EvidenceQuoteMatchMethod.FUZZY
    assert resolved.text == source.removesuffix(" Id., at 570.")


def test_evidence_quote_resolution_does_not_fuzz_negation() -> None:
    """Leniency cannot silently reverse the meaning of quoted evidence."""
    source = "The court concludes that knowledge cannot replace proper service in this action."
    proposed = "The court concludes that knowledge can replace proper service in this action."

    assert resolve_evidence_quote(source, proposed) is None


def test_mellea_pinpoint_check_stores_the_canonical_source_slice(monkeypatch: object) -> None:
    """The node stores source offsets and text rather than model-provided offsets."""
    citing_document = (
        "The court held that actual knowledge cannot replace service. See Example v. Case, 10 F.3d 20, 24."
    )
    matched = "Example v. Case, 10 F.3d 20, 24"
    start = citing_document.index(matched)
    validation = CitationValidation(
        citation=ExtractedCitation(
            citation_id="citation-1",
            span=Span(start, start + len(matched)),
            locator_span=Span(start + len("Example v. Case, "), start + len("Example v. Case, 10 F.3d 20")),
            matched_text="10 F.3d 20",
            citation=FullCaseCitation(
                volume="10",
                reporter="F.3d",
                page="20",
                pin_cite="24",
            ),
        )
    )
    page_text = "*24 The court concludes that actual knowledge cannot replace proper service in this action."
    retrieval = ReporterPageRetrievalNode(
        node_id="citation-1:reporter_page_retrieval",
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=ReporterPageRetrievalOutcome.FOUND,
        cluster_id="1",
        reporter_citation="10 F.3d 20",
        pin_cite="24",
        citation_index=1,
        evidence=ReporterPageEvidence(
            opinion_id="2",
            opinion_type="020lead",
            text=page_text,
        ),
        depends_on=("citation-1:opinion_candidate_evaluation:1",),
    )
    proposition_text = "The court held that actual knowledge cannot replace service."
    proposition_start = citing_document.index(proposition_text)
    proposition = MelleaCitingPropositionExtractionNode(
        node_id=f"{retrieval.node_id}:mellea_citing_proposition_extraction",
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=MelleaCitingPropositionExtractionOutcome.IDENTIFIED,
        context_span=Span(0, len(citing_document)),
        reasoning="The sentence immediately attributes this proposition to the citation.",
        proposition=proposition_text,
        proposition_span=Span(
            proposition_start,
            proposition_start + len(proposition_text),
        ),
        proposition_match_method=EvidenceQuoteMatchMethod.EXACT,
        proposition_match_score=1.0,
        depends_on=(retrieval.node_id,),
    )

    async def fake_run(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(
            success=True,
            result=SimpleNamespace(
                value=(
                    '{"verdict":"supports","reasoning":"The cited page states the attributed rule.",'
                    '"evidence_quote":"The court concludes that actual notice cannot replace '
                    'proper service in this action."}'
                )
            ),
        )

    config = SimpleNamespace(mellea_call_options=lambda **_kwargs: {})
    monkeypatch.setattr(
        "mellea_lrc.validation.pinpoint_retrieval.mellea_pinpoint_check.run_instruct_ivr",
        fake_run,
    )
    monkeypatch.setattr(
        "mellea_lrc.validation.pinpoint_retrieval.mellea_pinpoint_check.llm_api_config_from_env",
        lambda _environ: config,
    )

    node = asyncio.run(
        run_mellea_pinpoint_check(
            validation,
            retrieval=retrieval,
            proposition=proposition,
            session=object(),  # type: ignore[arg-type]
        )
    )

    assert node.status is ValidationNodeStatus.SUCCEEDED
    assert node.outcome is MelleaPinpointCheckOutcome.SUPPORTS
    assert node.evidence_match_method is EvidenceQuoteMatchMethod.FUZZY
    assert node.evidence_span is not None
    assert page_text[node.evidence_span.start : node.evidence_span.end] == node.evidence_quote
    assert "actual knowledge" in (node.evidence_quote or "")
    assert "actual notice" not in (node.evidence_quote or "")
    assert node.depends_on == (retrieval.node_id, proposition.node_id)
