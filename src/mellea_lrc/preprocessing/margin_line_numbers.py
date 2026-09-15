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

## When the position cannot answer

Some filings number the **right** margin, and there Docling merges most of the
numbers into the end of the prose item beside them -- `'... In re Motors
Liquidation Co., 957 F.3d 357, 23'` is one text item. The survivors still form
a column at the page edge, but the prose items built around the absorbed ones
begin at that same edge, so the column is not *left* of the prose and the
position test cannot separate them::

    page 2   prose left median 23.3   column of 9 at right edge 38.4

A second reading answers what position cannot: **line numbers count**. They
rise by one down the page, and where some were absorbed the survivors still
rise, in runs with gaps where the absorbed ones were -- `[27, 28, 33, 34, 35,
36, 37, 38, 39]`. A numeric column in a table holds quantities, which repeat and
fall. So a column is also a margin when it counts down the page and sits within
a margin's width of the page edge.

What this does not reach is the number Docling has already put inside a prose
item. Removing that would mean editing the text, which no rule here does.

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
from itertools import pairwise
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
# How far into a page a margin reaches, in points. A column of counting numbers
# this close to the edge of a letter page is a margin whatever Docling thinks
# the prose begins at -- which on a filing whose numbers it merges into the
# lines beside them is the same edge as the numbers themselves.
_MARGIN_EDGE = 60.0


def reclassify_margin_line_numbers(document: DoclingDocument) -> None:
    """Move this document's margin line numbers to the furniture layer, in place."""
    from docling_core.types.doc.common.content_layer import ContentLayer

    for item in _margin_items(document):
        item.content_layer = ContentLayer.FURNITURE


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
            if len(column) < MIN_MARGIN_NUMBERS:
                continue
            right = _placement(column[0])[1].r
            if right <= edge or (_counts_down_the_page(column) and right <= _MARGIN_EDGE):
                found.extend(column)
    return found


def _counts_down_the_page(column: list[Any]) -> bool:
    """Whether the column's numbers increase from top to bottom.

    Line numbers count. A numeric column in a table holds quantities, which may
    repeat and may fall, and the numbers a margin holds do neither: they rise by
    one down the page, and where Docling has absorbed some of them into the
    prose beside them the survivors still rise, in runs with gaps where the
    absorbed ones were.
    """
    values = [
        _line_number_value(getattr(item, "text", "") or "")
        for item in sorted(column, key=lambda entry: -_placement(entry)[1].t)
    ]
    return all(
        earlier is not None and later is not None and earlier < later for earlier, later in pairwise(values)
    )


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
