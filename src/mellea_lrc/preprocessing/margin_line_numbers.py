"""Reclassify pleading-paper margin line numbers as page furniture.

California, Nevada and Arizona pleading paper numbers every line of the page in
a narrow left margin. Docling reads that margin correctly -- as one text item
per number, each with its own bounding box -- but files the items under the
`body` content layer rather than `furniture`, alongside the page headers and
footers they otherwise resemble. `export_to_text` keeps the body and drops the
furniture, so the numbers survive into the plain text as a column of integers
that lands wherever the page happened to break::

    ... decision in Advanced Textile , 214 F.3d

    1

    2
    ...
    28

    1058 (9th Cir. 2000), as restricting

The citation is `214 F.3d 1058`, and nothing about it was damaged. It was
interrupted, by material that is not part of the sentence and is not part of
the document's running text at all.

Recognising that from the plain text alone means guessing from the shape of the
digits. In the structured document it is not a guess. The margin is a column:
its numbers share a right edge, they stack down the page, and the column sits
clear of where the prose begins.

    document 022, page 7    margin r = 60.0     prose l = 72.0
    document 011, page 1    margin r = 87.8     prose l = 104.4

So a run of numbers is a margin when it is **a column of bare integers, aligned
on the right, left of the page's prose**. All three conditions carry weight:
alignment separates a margin from numbers that merely happen to be short, the
count separates it from a stray figure, and the position separates it from a
numeric column inside a table.

The prose edge is taken as the **median** left edge of the page's non-numeric
items rather than the minimum. Docling does not always separate the margin
cleanly -- on some pages it absorbs the first few line numbers into the text
item beside them, as `'1 JULIE A. TOTTEN (STATE BAR NO. 166470)'`, and that
item's box starts out in the margin. One such item drags a minimum across the
column boundary and defeats the test; it does not move a median.

Items are moved to `furniture` rather than deleted, because that is what they
are, and because it is the classification Docling already gives the page
headers and footers that share the margin. Nothing downstream has to change:
the existing export keeps the body and drops the furniture.
"""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import median
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docling_core.types.doc.document import DoclingDocument

# `- 4 -` and `4` are both written in these margins.
_BARE_INTEGER = re.compile(r"^-?\s*(\d{1,3})\s*-?$")
# Line numbers run to the page's line count. A three-digit number in a margin is
# something else, and a reporter page must never be mistaken for one.
MAX_LINE_NUMBER = 99
# Pleading paper numbers 28 lines, but the column is only partly separated on
# some pages, so a run is often shorter. Five aligned integers in a column is
# already not something prose produces.
MIN_MARGIN_NUMBERS = 5
# Right edges within a column agree to well under a character width; the slack
# covers the extra digit of a two-digit number overhanging its neighbours.
_ALIGNMENT_SLACK = 5.0


def reclassify_margin_line_numbers(document: DoclingDocument) -> int:
    """Move this document's margin line numbers to the furniture layer.

    Returns how many items were moved. The document is modified in place.
    """
    from docling_core.types.doc.common.content_layer import ContentLayer

    moved = 0
    for item in _margin_items(document):
        if item.content_layer is not ContentLayer.FURNITURE:
            item.content_layer = ContentLayer.FURNITURE
            moved += 1
    return moved


def margin_line_numbers(document: DoclingDocument) -> list[str]:
    """Return the self-refs of every item this rule considers a margin number."""
    return [item.self_ref for item in _margin_items(document)]


def _margin_items(document: DoclingDocument) -> list[Any]:
    """Every text item that belongs to a page's left-margin number column."""
    numeric: dict[int, list[Any]] = defaultdict(list)
    prose_left: dict[int, list[float]] = defaultdict(list)

    # A document carrying no text layer has no margin to find. Docling's own
    # documents always have one, but the attribute is read defensively because
    # the rule now runs on every conversion: a shape it does not recognise
    # should yield no margin, not stop the preprocessing of the document.
    for item in getattr(document, "texts", None) or []:
        page, box = _placement(item)
        if box is None:
            continue
        if _line_number_value(getattr(item, "text", "") or "") is None:
            prose_left[page].append(box.l)
        else:
            numeric[page].append(item)

    found: list[Any] = []
    for page, items in numeric.items():
        if page not in prose_left:
            continue
        edge = median(prose_left[page])
        for column in _right_aligned_columns(items):
            if len(column) >= MIN_MARGIN_NUMBERS and _placement(column[0])[1].r <= edge:
                found.extend(column)
    return found


def _right_aligned_columns(items: list[Any]) -> list[list[Any]]:
    """Group items into columns that share a right edge.

    Line numbers are set flush right in their margin, so a two-digit number
    reaches further left than a one-digit one but ends in the same place. The
    right edge is what the column agrees on.
    """
    columns: list[list[Any]] = []
    for item in sorted(items, key=lambda entry: _placement(entry)[1].r):
        right = _placement(item)[1].r
        if columns and right - _placement(columns[-1][0])[1].r <= _ALIGNMENT_SLACK:
            columns[-1].append(item)
        else:
            columns.append([item])
    return columns


def _line_number_value(text: str) -> int | None:
    """The integer a margin number would carry, if this text is one at all."""
    match = _BARE_INTEGER.match(text.strip())
    if match is None:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= MAX_LINE_NUMBER else None


def _placement(item: Any) -> tuple[int, Any]:
    """The page and bounding box of an item's first provenance record."""
    provenance = getattr(item, "prov", None) or []
    if not provenance:
        return (-1, None)
    return (provenance[0].page_no, provenance[0].bbox)
