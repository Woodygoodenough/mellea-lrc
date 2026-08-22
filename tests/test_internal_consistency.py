"""Tests for finding citations a filing contradicts itself about."""

from __future__ import annotations

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.core.spans import Span
from mellea_lrc.extraction import ExtractedCitation
from mellea_lrc.extraction.citation_tree import build_citation_tree
from mellea_lrc.extraction.internal_consistency import inconsistent_citations
from mellea_lrc.extraction.types import ExtractedDocument, ExtractionMetadata
from mellea_lrc.preprocessing.plain_text import preprocess_plain_text_from_string


def _cite(
    index: int, plaintiff: str, defendant: str, volume: str, reporter: str, page: str
) -> ExtractedCitation:
    return ExtractedCitation(
        citation_id=f"c{index}",
        span=Span(index * 60, index * 60 + 20),
        locator_span=Span(index * 60, index * 60 + 20),
        matched_text=f"{volume} {reporter} {page}",
        citation=FullCaseCitation(
            volume=volume, reporter=reporter, page=page, plaintiff=plaintiff, defendant=defendant
        ),
    )


def _tree(*citations: ExtractedCitation):
    source = preprocess_plain_text_from_string("x" * 900)
    document = ExtractedDocument(
        source_metadata=source.source_metadata,
        preprocessing_metadata=source.preprocessing_metadata,
        text=source.text,
        citations=citations,
        extraction_metadata=ExtractionMetadata(),
    )
    return build_citation_tree(document)


def test_one_case_given_two_volumes_in_one_series_is_reported() -> None:
    """The case this exists for, taken from a real filing.

    A brief cites Liu v. Noem at the same page, court and year, as volume 708
    in one place and 780 in another. One of them has a transposed digit, and
    the filing establishes that on its own.
    """
    tree = _tree(
        _cite(0, "Liu", "Noem", "708", "F. Supp. 3d", "386"),
        _cite(1, "Liu", "Noem", "780", "F. Supp. 3d", "386"),
    )

    (found,) = inconsistent_citations(tree)

    assert found.citations == (("708", "386"), ("780", "386"))
    assert "708 F. Supp. 3d 386 and 780 F. Supp. 3d 386" in found.description


def test_parallel_citations_are_not_a_contradiction() -> None:
    """A case is routinely reported in several places at once.

    International Shoe is 326 U.S. 310 and 66 S. Ct. 154 and 90 L. Ed. 95, all
    correct. 60 of the 62 multiply-cited names across the two corpora are of
    this kind, so treating them as errors would bury the real ones.
    """
    tree = _tree(
        _cite(0, "International Shoe Co.", "Washington", "326", "U.S.", "310"),
        _cite(1, "International Shoe Co.", "Washington", "66", "S. Ct.", "154"),
        _cite(2, "International Shoe Co.", "Washington", "90", "L. Ed.", "95"),
    )

    assert inconsistent_citations(tree) == ()


def test_westlaw_citations_are_left_alone() -> None:
    """A Westlaw number identifies an opinion, not a case.

    One case carries several across its history, so a brief citing two of them
    for the same parties is usually citing two rulings.
    """
    tree = _tree(
        _cite(0, "Anderson", "United Airlines", "2023", "WL", "5721594"),
        _cite(1, "Anderson", "United Airlines", "2024", "WL", "1555496"),
    )

    assert inconsistent_citations(tree) == ()


def test_a_case_cited_consistently_is_not_reported() -> None:
    """Repeating a citation correctly is the ordinary case and must stay silent."""
    tree = _tree(
        _cite(0, "Liu", "Noem", "780", "F. Supp. 3d", "386"),
        _cite(1, "Liu", "Noem", "780", "F. Supp. 3d", "386"),
    )

    assert inconsistent_citations(tree) == ()


def test_a_missing_party_name_is_not_compared() -> None:
    """Without both names, two different cases can share a fragment.

    Reporting those as one contradiction would invent a defect out of an
    extraction shortfall.
    """
    tree = _tree(
        _cite(0, "Smith", "", "100", "F.3d", "1"),
        _cite(1, "Smith", "", "200", "F.3d", "2"),
    )

    assert inconsistent_citations(tree) == ()


def test_two_different_cases_clashing_are_both_reported() -> None:
    """One finding must not hide another in the same series."""
    tree = _tree(
        _cite(0, "Liu", "Noem", "708", "F. Supp. 3d", "386"),
        _cite(1, "Liu", "Noem", "780", "F. Supp. 3d", "386"),
        _cite(2, "Doe", "Roe", "500", "F. Supp. 3d", "10"),
        _cite(3, "Doe", "Roe", "501", "F. Supp. 3d", "10"),
    )

    assert len(inconsistent_citations(tree)) == 2
