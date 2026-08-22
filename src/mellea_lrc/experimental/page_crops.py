"""Cut a picture of the page out of the PDF, for the places text cannot explain.

Most layout damage has a shape a rule can recognise, and where a rule works it
should be used: it is exact, it costs nothing, and it puts no generated text
underneath the offsets everything downstream depends on. But some damage has no
repeatable shape, and for those a rule can only decline.

For a site like that the page itself is still available, and it holds
everything the exported text threw away -- what is a column and what is a
sentence, which text is a running head, where a line ends, what is italic. This
turns a span of the exported text back into the region of the page it was
printed in, and cuts that region out as an image, so a model can be asked what
it is looking at instead of being handed the wreckage of it.

Two facts make the mapping exact rather than approximate:

- Docling gives every text item a bounding box in PDF points, with the origin
  at the bottom left of the page, alongside the page's own height.
- Items appear in the exported text in the order Docling emits them, so each
  item's text can be found by scanning forward from the end of the last one.
  On false-citation-bench this locates 7,842 of 7,842 body items.

A span that crosses a page break produces one crop per page, which is not an
edge case: it is the situation that motivated the whole thing, since a citation
broken across pages is exactly what neither half of the text explains.

Nothing here is wired into the pipeline. It is the tool for the residue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from docling_core.types.doc.document import DoclingDocument

    from mellea_lrc.core.spans import Span

# Three times PDF points reads comfortably and keeps a page crop well inside
# what a vision model will accept without being resized down again.
DEFAULT_SCALE = 3.0
# Enough margin to show the line above and below, which is usually where the
# explanation is: the sentence a fragment belongs to, or the column beside it.
DEFAULT_PADDING_POINTS = 14.0


@dataclass(frozen=True, slots=True)
class ItemPlacement:
    """Where one text item sits, both in the exported text and on the page."""

    start: int
    end: int
    page_no: int
    left: float
    top: float
    right: float
    bottom: float

    def overlaps(self, start: int, end: int) -> bool:
        """Whether this item shares any character with the given range."""
        return self.start < end and start < self.end


def place_text_items(document: DoclingDocument) -> tuple[ItemPlacement, ...]:
    """Map every body text item to its span in the exported text and its box.

    Items are located by scanning forward rather than by rebuilding the text,
    because the export is not a plain join -- tables become markdown and list
    items gain a prefix. Scanning forward is safe for the same reason a rebuild
    would have been: the items come out in order.
    """
    from docling_core.types.doc.common.content_layer import ContentLayer

    text = document.export_to_text()
    placements, cursor = [], 0
    for item, _ in document.iterate_items(with_groups=False, included_content_layers={ContentLayer.BODY}):
        body = getattr(item, "text", None)
        provenance = getattr(item, "prov", None) or []
        if not body or not body.strip() or not provenance:
            continue
        found = text.find(body, cursor)
        if found == -1:
            continue
        box = provenance[0].bbox
        placements.append(
            ItemPlacement(
                start=found,
                end=found + len(body),
                page_no=provenance[0].page_no,
                left=box.l,
                top=box.t,
                right=box.r,
                bottom=box.b,
            )
        )
        cursor = found + len(body)
    return tuple(placements)


def regions_for_span(
    span: Span,
    placements: tuple[ItemPlacement, ...],
    *,
    padding: float = DEFAULT_PADDING_POINTS,
) -> tuple[tuple[int, tuple[float, float, float, float]], ...]:
    """The page regions a span was printed in, one per page it touches.

    A span crossing a page break yields two regions. That is the case worth
    having: neither page alone explains a citation split between them.
    """
    touched: dict[int, list[ItemPlacement]] = {}
    for placement in placements:
        if placement.overlaps(span.start, span.end):
            touched.setdefault(placement.page_no, []).append(placement)

    regions = []
    for page_no in sorted(touched):
        items = touched[page_no]
        regions.append(
            (
                page_no,
                (
                    min(item.left for item in items) - padding,
                    max(item.top for item in items) + padding,
                    max(item.right for item in items) + padding,
                    min(item.bottom for item in items) - padding,
                ),
            )
        )
    return tuple(regions)


def crop_region(
    pdf_path: Path | str,
    page_no: int,
    region: tuple[float, float, float, float],
    page_height: float,
    *,
    scale: float = DEFAULT_SCALE,
) -> Any:
    """Render one page and cut out a region given in PDF points.

    Docling measures from the bottom left of the page and image libraries
    measure from the top left, so the vertical coordinates are subtracted from
    the page height rather than used directly. Getting this backwards produces
    a crop of the wrong part of the page that still looks like a plausible
    piece of a legal document, which is why it is done in one place.
    """
    import pypdfium2

    pdf = pypdfium2.PdfDocument(str(pdf_path))
    try:
        image = pdf[page_no - 1].render(scale=scale).to_pil()
    finally:
        pdf.close()

    return image.crop(pixel_box(region, page_height, scale=scale, width=image.width, height=image.height))


def pixel_box(
    region: tuple[float, float, float, float],
    page_height: float,
    *,
    scale: float,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Convert a region in PDF points to a pixel box, and clamp it to the image.

    This is the whole of the coordinate conversion, kept separate because it is
    the one step with no visible symptom when it is wrong: a flipped vertical
    axis crops a different part of the page, and the result still looks like a
    plausible piece of a legal document.
    """
    left, top, right, bottom = region
    return (
        max(0, int(left * scale)),
        max(0, int((page_height - top) * scale)),
        min(width, int(right * scale)),
        min(height, int((page_height - bottom) * scale)),
    )


def crop_span(
    pdf_path: Path | str,
    document: DoclingDocument,
    span: Span,
    *,
    scale: float = DEFAULT_SCALE,
    padding: float = DEFAULT_PADDING_POINTS,
) -> list[tuple[int, Any]]:
    """Every page image a span was printed across, in page order."""
    placements = place_text_items(document)
    return [
        (
            page_no,
            crop_region(
                pdf_path,
                page_no,
                region,
                document.pages[page_no].size.height,
                scale=scale,
            ),
        )
        for page_no, region in regions_for_span(span, placements, padding=padding)
    ]
