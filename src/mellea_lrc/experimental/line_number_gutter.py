"""Blank the line-number gutter that pleading paper leaves inside citations.

California and Nevada pleading paper numbers every line in a left margin. PDF
extraction reads that margin as a block of its own, and when the block lands
mid-page it is emitted *between* the halves of whatever text spans the break::

    Advanced Textile , 214 F.3d

    1

    2
    ...
    28

    1058 (9th Cir. 2000), as restricting

The citation is `214 F.3d 1058` and every character of it survived extraction.
What separates the volume-reporter from the page is not damage to the citation
but a column of unrelated integers -- and a citation parser cannot tell the
difference. It either refuses the citation, or joins `214 F.3d` to the `1` at
the top of the gutter and then reports a confident verdict about a page the
document never cited. The second failure is the dangerous one, and it is the
reason the relaxed tokenizer bounds how far it will look for a page.

**The gutter is blanked, not deleted.** Each run is replaced by spaces of equal
length, so no offset moves and every span already measured against this text
stays valid -- the same choice the benchmark makes when it masks captions. What
remains between the two halves is ordinary horizontal whitespace, which the
layout-tolerant tokenizer already crosses. The blank lines that delimit the run
are blanked with it, since they belong to the gutter block rather than to the
sentence the gutter interrupted.

Detection is deliberately narrow. A run must be several one- or two-digit
integers, each alone on its line, ascending by exactly one. Prose does not look
like that. A numbered list does, which is why a run must *reach* a plausible
gutter length rather than merely start like one, and why the two-digit limit
matters: it keeps the pattern away from reporter volumes and pages, which is
the whole hazard being avoided here.
"""

from __future__ import annotations

import re
from itertools import pairwise

# Pleading paper numbers 28 lines, and a gutter fragment begins wherever the
# page break fell, so runs are usually partial. Six is long enough that an
# ascending run of them is a margin rather than a list of numbered paragraphs.
MIN_GUTTER_LINES = 6

_LINE = r"\d{1,2}\n[^\S\r\n]*\n[^\S\r\n]*"
_GUTTER = re.compile(rf"\n[^\S\r\n]*\n[^\S\r\n]*(?:{_LINE}){{{MIN_GUTTER_LINES},}}")


def blank_line_number_gutters(text: str) -> str:
    """Replace every margin line-number run with spaces of equal length.

    Offsets are preserved exactly, so this may be applied before extraction
    without invalidating any span measured against the original text.
    """
    result = text
    for start, end in reversed(gutter_runs(text)):
        result = result[:start] + " " * (end - start) + result[end:]
    return result


def gutter_runs(text: str) -> tuple[tuple[int, int], ...]:
    """Return the span of every line-number gutter run, in order."""
    return tuple(
        (match.start(), match.end())
        for match in _GUTTER.finditer(text)
        if _ascends_by_one([int(value) for value in match.group().split()])
    )


def _ascends_by_one(numbers: list[int]) -> bool:
    """Whether the run counts up one line at a time, as a margin gutter does."""
    return len(numbers) >= MIN_GUTTER_LINES and all(
        later - earlier == 1 for earlier, later in pairwise(numbers)
    )
