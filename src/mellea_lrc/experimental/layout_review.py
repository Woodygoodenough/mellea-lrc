"""Pick out the citations the tokenizer had to guess about.

A citation whose text runs unbroken is not in doubt. One the tokenizer only
matched by crossing a blank line is different: a blank line is where a page
ends, and what follows a page break is whatever the page furniture put there.
With the margins removed that is usually the citation's own page, which is the
whole reason the wider join is allowed at all -- but "usually" is the word that
makes it worth listing.

These are the sites to look at, and looking is now possible: `page_crops` turns
a span back into the region of the page it was printed in, so the question
"what is actually there" can be answered from the page rather than from the
text that lost the answer.

The measure is deliberately crude, because it is a trigger rather than a
verdict. A blank line inside a citation is rare, so listing every one costs
little; deciding which of them is wrong is the part that needs the picture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mellea_lrc.extraction.types import ExtractedCitation, ExtractedDocument

# One newline is an ordinary wrapped line. Two is a block boundary, and past a
# block boundary the tokenizer is relying on the text having been cleaned.
_BLANK_LINE = re.compile(r"\r?\n[^\S\r\n]*\r?\n")


@dataclass(frozen=True, slots=True)
class LayoutReviewSite:
    """One citation that was only matched by reaching across a page break."""

    citation: ExtractedCitation
    blank_lines: int

    @property
    def citation_id(self) -> str:
        """The extracted citation's identifier."""
        return self.citation.citation_id


def sites_needing_review(document: ExtractedDocument) -> tuple[LayoutReviewSite, ...]:
    """Every citation whose own text contains a blank line."""
    found = []
    for citation in document.citations:
        breaks = len(_BLANK_LINE.findall(citation.matched_text))
        if breaks:
            found.append(LayoutReviewSite(citation=citation, blank_lines=breaks))
    return tuple(found)
