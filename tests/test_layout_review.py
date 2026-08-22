"""Tests for listing the citations the tokenizer reached across a break for."""

from __future__ import annotations

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.core.spans import Span
from mellea_lrc.experimental.layout_review import sites_needing_review
from mellea_lrc.extraction import ExtractedCitation
from mellea_lrc.extraction.types import ExtractedDocument, ExtractionMetadata
from mellea_lrc.preprocessing.plain_text import preprocess_plain_text_from_string


def _document(*matched: str) -> ExtractedDocument:
    source = preprocess_plain_text_from_string("x" * 800)
    citations = tuple(
        ExtractedCitation(
            citation_id=f"c{index}",
            span=Span(index * 40, index * 40 + len(text)),
            locator_span=Span(index * 40, index * 40 + len(text)),
            matched_text=text,
            citation=FullCaseCitation(volume="214", reporter="F.3d", page="1058"),
        )
        for index, text in enumerate(matched)
    )
    return ExtractedDocument(
        source_metadata=source.source_metadata,
        preprocessing_metadata=source.preprocessing_metadata,
        text=source.text,
        citations=citations,
        extraction_metadata=ExtractionMetadata(),
    )


def test_a_citation_reaching_across_a_page_break_is_listed() -> None:
    """This is the one the tokenizer only matched because the text was cleaned."""
    document = _document("214 F.3d\n\n1058")

    (site,) = sites_needing_review(document)

    assert site.citation_id == "c0"
    assert site.blank_lines == 1


def test_an_unbroken_citation_is_not_listed() -> None:
    """Most citations are not in doubt, and listing them would drown the rest."""
    assert sites_needing_review(_document("214 F.3d 1058")) == ()


def test_a_wrapped_line_is_not_a_page_break() -> None:
    """One newline is ordinary wrapping; two is a block boundary."""
    assert sites_needing_review(_document("214 F.3d\n1058")) == ()


def test_a_blank_line_carrying_spaces_still_counts() -> None:
    """Extraction leaves trailing spaces on blank lines often enough to matter."""
    document = _document("214 F.3d\n   \n1058")

    (site,) = sites_needing_review(document)

    assert site.blank_lines == 1


def test_every_break_in_one_citation_is_counted() -> None:
    """More breaks is more doubt, and the count is what orders a review queue."""
    document = _document("214 F.3d\n\n1058\n\n(9th Cir. 2000)")

    (site,) = sites_needing_review(document)

    assert site.blank_lines == 2
