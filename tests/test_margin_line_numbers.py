"""Tests for reclassifying pleading-paper margin line numbers as furniture."""

from __future__ import annotations

import pytest

pytest.importorskip("docling_core", reason="Docling is an optional preprocessing dependency")

from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.common.reference import ProvenanceItem
from docling_core.types.doc.document import DoclingDocument

from mellea_lrc.preprocessing.margin_line_numbers import (
    margin_line_numbers,
    reclassify_margin_line_numbers,
)

# The real geometry, read off document 022 of false-citation-bench.
GUTTER_LEFT, GUTTER_RIGHT = 47.5, 60.0
PROSE_LEFT, PROSE_RIGHT = 72.0, 543.4


def _document() -> DoclingDocument:
    return DoclingDocument(name="filing")


def _add(
    document: DoclingDocument,
    text: str,
    *,
    left: float,
    right: float,
    page: int = 1,
    label: str = "text",
) -> object:
    return document.add_text(
        label=label,
        text=text,
        prov=ProvenanceItem(
            page_no=page,
            bbox=BoundingBox(l=left, t=100.0, r=right, b=90.0),
            charspan=(0, len(text)),
        ),
    )


def _pleading_page(document: DoclingDocument, *prose: str, page: int = 1, lines: int = 28) -> None:
    """One page of pleading paper: a numbered left margin, then the prose."""
    for number in range(1, lines + 1):
        _add(document, str(number), left=GUTTER_LEFT, right=GUTTER_RIGHT, page=page)
    for line in prose:
        _add(document, line, left=PROSE_LEFT, right=PROSE_RIGHT, page=page)


def test_a_citation_broken_across_a_page_is_made_whole() -> None:
    """The case this exists for: the margin of page 8 fell inside the citation.

    Page 7 ends mid-sentence at `214 F.3d`; page 8 opens with its own line
    numbers and only then continues `1058`. Nothing about the citation was
    damaged -- it was interrupted by material that is not part of the text.
    """
    document = _document()
    _pleading_page(document, "decision in Advanced Textile , 214 F.3d", page=7)
    _pleading_page(document, "1058 (9th Cir. 2000), as restricting", page=8)

    reclassify_margin_line_numbers(document)

    assert document.export_to_text() == (
        "decision in Advanced Textile , 214 F.3d\n\n1058 (9th Cir. 2000), as restricting"
    )


def test_every_margin_number_is_moved_and_nothing_else_is() -> None:
    """Two pages of pleading paper is fifty-six numbers and no lost prose."""
    document = _document()
    _pleading_page(document, "first page prose", page=1)
    _pleading_page(document, "second page prose", page=2)

    assert reclassify_margin_line_numbers(document) == 56
    assert document.export_to_text() == "first page prose\n\nsecond page prose"


def test_a_numbered_list_in_the_body_is_not_a_margin() -> None:
    """Position is half the test, and it is the half prose cannot fake.

    A list item carries a bare integer just as a margin number does. It sits in
    the text column, so it stays.
    """
    document = _document()
    for number in range(1, 9):
        _add(document, str(number), left=PROSE_LEFT, right=PROSE_RIGHT, label="list_item")

    assert margin_line_numbers(document) == []


def test_prose_in_a_narrow_left_column_is_not_a_margin() -> None:
    """Being numeric is the other half, and it is the half geometry cannot fake."""
    document = _document()
    _add(document, "Plaintiff", left=GUTTER_LEFT, right=GUTTER_RIGHT)
    _add(document, "body text", left=PROSE_LEFT, right=PROSE_RIGHT)

    assert margin_line_numbers(document) == []


def test_a_reporter_page_alone_on_a_line_is_never_a_margin_number() -> None:
    """`1058` is the value the whole exercise is trying to protect."""
    document = _document()
    _add(document, "1058", left=PROSE_LEFT, right=PROSE_RIGHT)

    assert margin_line_numbers(document) == []
    assert "1058" in document.export_to_text()


def test_a_three_digit_number_in_the_margin_is_left_alone() -> None:
    """Margins count lines on a page; they do not reach three digits."""
    document = _document()
    _add(document, "404", left=GUTTER_LEFT, right=GUTTER_RIGHT)
    _add(document, "body text", left=PROSE_LEFT, right=PROSE_RIGHT)

    assert margin_line_numbers(document) == []


def test_the_dashed_margin_style_is_recognised() -> None:
    """Some of these filings write the margin as `- 4 -` rather than `4`."""
    document = _document()
    for number in range(1, 9):
        _add(document, f"- {number} -", left=GUTTER_LEFT, right=GUTTER_RIGHT)
    _add(document, "body text", left=PROSE_LEFT, right=PROSE_RIGHT)

    assert len(margin_line_numbers(document)) == 8


def test_a_lone_number_in_the_margin_is_not_a_column() -> None:
    """One number is a stray, not a margin, and removing it could lose content."""
    document = _document()
    _add(document, "4", left=GUTTER_LEFT, right=GUTTER_RIGHT)
    _add(document, "body text", left=PROSE_LEFT, right=PROSE_RIGHT)

    assert margin_line_numbers(document) == []


def test_an_absorbed_line_number_does_not_defeat_the_page() -> None:
    """Docling sometimes glues the first line numbers onto the text beside them.

    That item's box starts out in the margin, so the page's *minimum* left edge
    lands inside the column and every real margin item then tests as being to
    the right of the prose. A median is unmoved by a few such items, which is
    why the prose edge is measured with one -- this is document 011, page 1.
    """
    document = _document()
    for absorbed in ("1 JULIE A. TOTTEN (STATE BAR NO. 166470)", "3 ORRICK, HERRINGTON LLP"):
        _add(document, absorbed, left=GUTTER_LEFT, right=PROSE_RIGHT)
    for line in ("The Orrick Building", "San Francisco, CA", "Attorneys for Defendant"):
        _add(document, line, left=PROSE_LEFT, right=PROSE_RIGHT)
    for number in range(6, 29):
        _add(document, str(number), left=GUTTER_LEFT, right=GUTTER_RIGHT)

    assert len(margin_line_numbers(document)) == 23


def test_a_page_of_nothing_but_numbers_is_left_alone() -> None:
    """With no prose to measure against, there is no margin to be left of.

    Declining is the safe direction: leaving a real margin in costs recall,
    while removing real content costs a citation outright.
    """
    document = _document()
    for number in range(1, 29):
        _add(document, str(number), left=GUTTER_LEFT, right=GUTTER_RIGHT)

    assert margin_line_numbers(document) == []


def test_furniture_is_not_counted_twice() -> None:
    """Re-running the rule reports no further work, and changes nothing."""
    document = _document()
    _pleading_page(document, "prose")

    assert reclassify_margin_line_numbers(document) == 28
    assert reclassify_margin_line_numbers(document) == 0


def test_an_item_without_provenance_is_left_alone() -> None:
    """Not every backend records geometry; without it this rule cannot judge."""
    document = _document()
    document.add_text(label="text", text="7")
    _add(document, "body text", left=PROSE_LEFT, right=PROSE_RIGHT)

    assert margin_line_numbers(document) == []
    assert document.export_to_text() == "7\n\nbody text"


def test_a_document_with_no_text_layer_has_no_margin() -> None:
    """The rule runs on every conversion, so an unrecognised shape must not raise.

    A stub document, or a Docling version exposing its items differently, has
    no margin to find. Reaching straight for the attribute stopped preprocessing
    outright rather than reporting that nothing was removed.
    """

    class Bare:
        pass

    assert reclassify_margin_line_numbers(Bare()) == 0
