"""Where in the filing each field of a citation has to come from.

A case name is written before its locator and a court and date after it, in
the parenthetical. A reading of either that comes from anywhere else is a
reading of some other citation. So the text a model may read a field from is
bounded by the citation's neighbours, in the same way the extraction branch
bounds its own re-read of the parenthetical: at the next citation that is not
co-located with this one.

Co-location is what makes the rule more than "between the locators". A
parallel citation -- `Ashcroft v. Iqbal, 556 U.S. 662, 129 S. Ct. 1937 (2009)`
-- is two locators, one name and one parenthetical. The name sits before the
first locator and belongs to both; the parenthetical sits after the last and
belongs to both. Each member's name window therefore runs back from the
group's first locator, and each member's parenthetical window runs forward
from its own locator past its co-located neighbours to the next citation that
is not one of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mellea_lrc.core.spans import Span

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mellea_lrc.extraction.types import ExtractedCitation

MAX_NAME_CHARS = 300
"""How far back from the locator a case name may start. A caption that long
is a caption of several parties; anything further back is a sentence."""
MAX_PARENTHETICAL_CHARS = 300
"""How far forward the court and date may sit, matching eyecite's own limit."""


@dataclass(frozen=True, slots=True)
class CitationWindows:
    """The two regions of the filing one citation's fields may be read from."""

    name: Span
    """Before the locator: where the case name is."""
    parenthetical: Span
    """After the locator: where the court and date are."""


def windows_for(
    item: ExtractedCitation, citations: Sequence[ExtractedCitation], length: int
) -> CitationWindows:
    """The windows for one citation, bounded by its non-co-located neighbours."""
    group = [
        other
        for other in citations
        if other is item or (item.colocation_id is not None and other.colocation_id == item.colocation_id)
    ]
    first_locator = min(other.locator_span.start for other in group)
    last_locator = max(other.locator_span.end for other in group)

    def unrelated(other: ExtractedCitation) -> bool:
        return other not in group

    previous_ends = [
        other.full_span.end
        for other in citations
        if unrelated(other) and other.full_span.end <= first_locator
    ]
    next_starts = [
        other.locator_span.start
        for other in citations
        if unrelated(other) and other.locator_span.start >= last_locator
    ]
    name_start = max([*previous_ends, first_locator - MAX_NAME_CHARS, 0])
    parenthetical_end = min([*next_starts, item.locator_span.end + MAX_PARENTHETICAL_CHARS, length])
    return CitationWindows(
        name=Span(name_start, first_locator),
        parenthetical=Span(item.locator_span.end, max(item.locator_span.end, parenthetical_end)),
    )
