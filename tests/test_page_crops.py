"""Tests for turning a span of exported text back into a region of the page."""

from __future__ import annotations

import pytest

pytest.importorskip("docling_core", reason="Docling is an optional preprocessing dependency")

from docling_core.types.doc.base import BoundingBox, CoordOrigin  # noqa: E402
from docling_core.types.doc.common.reference import ProvenanceItem  # noqa: E402
from docling_core.types.doc.document import DoclingDocument  # noqa: E402

from mellea_lrc.core.spans import Span  # noqa: E402
from mellea_lrc.experimental.page_crops import (  # noqa: E402
    pixel_box,
    place_text_items,
    regions_for_span,
)

PAGE_HEIGHT = 792.0


def _document(*lines: tuple[str, int, float, float, float, float]) -> DoclingDocument:
    """Build a document from (text, page, left, top, right, bottom)."""
    document = DoclingDocument(name="filing")
    for text, page, left, top, right, bottom in lines:
        document.add_text(
            label="text",
            text=text,
            prov=ProvenanceItem(
                page_no=page,
                bbox=BoundingBox(l=left, t=top, r=right, b=bottom, coord_origin=CoordOrigin.BOTTOMLEFT),
                charspan=(0, len(text)),
            ),
        )
    return document


# The real shape of document 022: a sentence ending page 7 and continuing on 8.
SPLIT = (
    ("decision in Advanced Textile , 214 F.3d", 7, 108.0, 101.3, 546.7, 90.1),
    ("1058 (9th Cir. 2000), as restricting anonymity", 8, 72.0, 716.7, 543.4, 595.0),
)


def test_each_item_is_placed_at_its_own_text() -> None:
    """The span recorded for an item must address that item and nothing else."""
    document = _document(*SPLIT)
    text = document.export_to_text()

    placements = place_text_items(document)

    assert len(placements) == 2
    for placement, (body, *_rest) in zip(placements, SPLIT, strict=True):
        assert text[placement.start : placement.end] == body


def test_a_span_crossing_a_page_break_yields_a_region_on_each_page() -> None:
    """This is the case the module exists for.

    Neither page explains the citation on its own: page 7 ends at `214 F.3d`
    and page 8 opens with `1058`. One crop of either would show a fragment.
    """
    document = _document(*SPLIT)
    text = document.export_to_text()
    start = text.index("214 F.3d")
    span = Span(start, text.index("1058") + len("1058"))

    regions = regions_for_span(span, place_text_items(document))

    assert [page for page, _ in regions] == [7, 8]


def test_a_region_covers_every_item_the_span_touches_on_that_page() -> None:
    """Two items on one page become one region enclosing both."""
    document = _document(
        ("left column text", 3, 72.0, 700.0, 200.0, 690.0),
        ("right column text", 3, 300.0, 720.0, 540.0, 640.0),
    )
    text = document.export_to_text()
    span = Span(0, len(text))

    ((page, region),) = regions_for_span(span, place_text_items(document), padding=0.0)

    assert page == 3
    assert region == (72.0, 720.0, 540.0, 640.0)


def test_padding_widens_the_region_on_every_side() -> None:
    """The line above and below is usually where the explanation is."""
    document = _document(("a line", 1, 100.0, 500.0, 400.0, 480.0))
    span = Span(0, len("a line"))

    ((_, region),) = regions_for_span(span, place_text_items(document), padding=10.0)

    assert region == (90.0, 510.0, 410.0, 470.0)


def test_a_span_touching_nothing_yields_no_region() -> None:
    """Better no picture than a picture of the wrong part of the page."""
    document = _document(("a line", 1, 100.0, 500.0, 400.0, 480.0))

    assert regions_for_span(Span(900, 950), place_text_items(document)) == ()


def test_the_vertical_axis_is_flipped_not_reused() -> None:
    """Docling measures up from the bottom; images measure down from the top.

    Getting this backwards crops a different part of the page and still returns
    something that looks like a legal document, so it is asserted directly.
    """
    region = (72.0, 700.0, 540.0, 600.0)

    box = pixel_box(region, PAGE_HEIGHT, scale=2.0, width=2000, height=2000)

    assert box == (144, int((792.0 - 700.0) * 2), 1080, int((792.0 - 600.0) * 2))
    assert box[1] < box[3]


def test_a_region_running_off_the_page_is_clamped() -> None:
    """Padding at a page edge must not ask for pixels that do not exist."""
    region = (-20.0, 800.0, 700.0, -10.0)

    box = pixel_box(region, PAGE_HEIGHT, scale=1.0, width=612, height=792)

    assert box == (0, 0, 612, 792)
