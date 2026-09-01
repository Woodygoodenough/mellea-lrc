"""Locate the table of authorities, which cites nothing.

A brief opens with an index of the cases it relies on:

    Doe v. Megless , 654 F.3d 404 (3d Cir. 2011) ...................... 8, 12, 13

That entry is a *listing*. It attaches no proposition to the case, makes no
claim about any page of it, and the numbers trailing the dot leaders are pages
of the brief rather than of the reporter. There is nothing in it that can be
right or wrong beyond the case existing.

Extraction cannot see the difference, because by the time the document is text
the index reads like any other run of citations. On false-citation-bench that
is **113 of 302 citation occurrences** in the seven filings that carry an
index -- 37% of them, every one asserting nothing. Counting those beside
citations a brief actually argues from inflates any coverage figure, and
sending them to a pinpoint check spends retrieval on a question nobody asked.

Docling already knows. It labels these tables `document_index`, distinctly from
an ordinary `table`, in 14 of the 20 tables across the corpus. This module
turns that label into character spans over the exported text, so a consumer can
tell an argued citation from an indexed one.

**The index is located, not removed**, because it is independently useful: it is
the document's own declaration of what it cites, and therefore a free check on
whether extraction found everything. An identifier listed in the index and
absent from the body is either a genuine index-only entry or an extraction
miss, and on this corpus the check finds a real one -- `759 F.2d 1032` in
document 007, which reaches the text as `759\\n\\nF.2d 1032` and is lost to the
production tokenizer.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from mellea_lrc.core.spans import Span

if TYPE_CHECKING:
    from docling_core.types.doc.document import DoclingDocument

INDEX_LABEL = "document_index"


def index_table_spans(document: DoclingDocument) -> tuple[Span, ...]:
    """Return the spans of the exported text occupied by index tables.

    Measured by rendering the document twice and taking the difference, rather
    than by searching the output for a table's text: an index entry can repeat
    verbatim elsewhere in a brief, and a search would have no way to tell which
    occurrence it had found.

    The document is left as it was found.
    """
    from docling_core.types.doc.common.content_layer import ContentLayer

    tables = [table for table in document.tables if table.label.value == INDEX_LABEL]
    if not tables:
        return ()

    with_index = document.export_to_text()
    restore = [table.content_layer for table in tables]
    try:
        for table in tables:
            table.content_layer = ContentLayer.FURNITURE
        without_index = document.export_to_text()
    finally:
        for table, layer in zip(tables, restore, strict=True):
            table.content_layer = layer

    return _removed_spans(with_index, without_index)


def _removed_spans(before: str, after: str) -> tuple[Span, ...]:
    """The regions of `before` that do not survive into `after`."""
    spans, position = [], 0
    for block in SequenceMatcher(None, before, after, autojunk=False).get_matching_blocks():
        if block.a > position:
            spans.append(Span(position, block.a))
        position = block.a + block.size
    if position < len(before):
        spans.append(Span(position, len(before)))
    return tuple(spans)


def is_within(span: Span, regions: tuple[Span, ...]) -> bool:
    """Whether a span falls inside any of the regions.

    Containment rather than overlap: a citation that merely abuts an index is
    argued text, and treating it as indexed would silently drop a real claim.
    """
    return any(region.start <= span.start and span.end <= region.end for region in regions)
