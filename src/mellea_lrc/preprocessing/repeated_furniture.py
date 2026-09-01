"""Catch page furniture Docling labelled inconsistently.

Docling labels the running head and foot of a page `page_header` and
`page_footer`, and `export_to_text` drops both. It does not always apply those
labels to the same thing on every page. In one filing the identical string

    Case 2:26-cv-05379-JAT   Document 13   Filed 08/07/26   Page 3 of 9

sits at the same coordinates on six pages and is labelled `page_header` on one
of them and `section_header` on the other five. The five stay in the body, and
one of them landed inside a citation's parenthetical, where eyecite read the
`9` of "Page 3 of 9" together with the date that followed and reported a
citation of `9 Mar. 10`.

The document contains the evidence needed to fix this. Docling got the label
right *somewhere*, and page furniture is by definition printed at the same
place on every page. So an item sitting at coordinates where this document has
a recognised header or footer is a header or footer, whatever label it was
given.

This finds three kinds of thing on the corpora measured:

- running heads that were labelled `section_header` or `text` on some pages;
- page numbers at the foot, labelled `page_footer` on one page and `text` on
  the rest;
- a firm name set sideways in the margin, in a box 7 points wide and 108 tall,
  labelled `page_header` on one page and `text` on another.

Boxes must agree on all four edges, not merely overlap. Running furniture is
printed from the same template on every page, so its coordinates repeat to
within a fraction of a point; anything needing a looser test is not the same
element, and a looser test would start matching first lines of body text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docling_core.types.doc.document import DoclingDocument

FURNITURE_LABELS = frozenset({"page_header", "page_footer"})
# Coordinates of repeated furniture agree to well under a point. Three is loose
# enough for rounding and tight enough that body text cannot reach it.
_BOX_TOLERANCE = 3.0


def reclassify_repeated_furniture(document: DoclingDocument) -> int:
    """Move body items sharing a box with a labelled header or footer to furniture.

    Returns how many items were moved. The document is modified in place.
    """
    from docling_core.types.doc.common.content_layer import ContentLayer

    moved = 0
    for item in repeated_furniture(document):
        if item.content_layer is not ContentLayer.FURNITURE:
            item.content_layer = ContentLayer.FURNITURE
            moved += 1
    return moved


def repeated_furniture(document: DoclingDocument) -> list[Any]:
    """Body items printed where this document has a recognised header or footer."""
    known = [
        _box(item)
        for item in document.texts
        if item.label.value in FURNITURE_LABELS and _box(item) is not None
    ]
    if not known:
        return []

    found = []
    for item in document.texts:
        if item.label.value in FURNITURE_LABELS:
            continue
        box = _box(item)
        if box is not None and any(_same_box(box, reference) for reference in known):
            found.append(item)
    return found


def _box(item: Any) -> tuple[float, float, float, float] | None:
    """The item's bounding box as (left, right, top, bottom)."""
    provenance = getattr(item, "prov", None) or []
    if not provenance:
        return None
    bbox = provenance[0].bbox
    return (bbox.l, bbox.r, bbox.t, bbox.b)


def _same_box(
    box: tuple[float, float, float, float],
    reference: tuple[float, float, float, float],
) -> bool:
    """Whether two boxes describe the same place on the page."""
    return all(abs(a - b) <= _BOX_TOLERANCE for a, b in zip(box, reference, strict=True))
