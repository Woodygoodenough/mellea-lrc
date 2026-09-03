"""Candidate margin-detection rules, written against cached page layout.

Each rule takes one document's text items -- plain dicts of text, label, page
and bounding box, as `scripts/dump_page_layout.py` records them -- and returns
the indices it judges to be margin numbers. Working on dicts rather than a
`DoclingDocument` keeps a variant to a few lines and lets the whole corpus be
scored without reconverting anything.

The shipped rule is `current`. Everything after it is an experiment, and the
comment above each says what evidence it adds and what it risks.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import pairwise
from statistics import median

Item = dict
Items = list[Item]

MAX_LINE_NUMBER = 99
ALIGNMENT_SLACK = 5.0


# --- shared primitives -------------------------------------------------------


def line_number_value(text: str) -> int | None:
    """The integer a margin number would carry, if this text is one at all."""
    stripped = text.strip().strip("-").strip()
    if not stripped.isdigit():
        return None
    value = int(stripped)
    return value if 1 <= value <= MAX_LINE_NUMBER else None


def by_page(items: Items) -> dict[int, list[int]]:
    """Indices of the items on each page."""
    pages: dict[int, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        pages[item["page"]].append(index)
    return pages


def prose_edge(items: Items, indices: list[int]) -> float | None:
    """Median left edge of the page's non-numeric items."""
    lefts = [items[i]["l"] for i in indices if line_number_value(items[i]["text"]) is None]
    return median(lefts) if lefts else None


def right_aligned_columns(items: Items, indices: list[int]) -> list[list[int]]:
    """Group numeric items into columns sharing a right edge."""
    columns: list[list[int]] = []
    for index in sorted(indices, key=lambda i: items[i]["r"]):
        if columns and items[index]["r"] - items[columns[-1][0]]["r"] <= ALIGNMENT_SLACK:
            columns[-1].append(index)
        else:
            columns.append([index])
    return columns


def numeric_indices(items: Items, indices: list[int]) -> list[int]:
    """The page's bare-integer items."""
    return [i for i in indices if line_number_value(items[i]["text"]) is not None]


def ascends_down_the_page(items: Items, column: list[int]) -> bool:
    """Whether the column's values increase as it descends the page.

    A margin is numbered top to bottom. A numeric column in a table carries
    arbitrary values, and a column of identical page numbers does not ascend at
    all. This is the cheapest evidence that separates the two, and it needs no
    position at all -- which is what makes it safe to lean on when the position
    test is the thing being loosened.
    """
    ordered = sorted(column, key=lambda i: -items[i]["t"])
    values = [line_number_value(items[i]["text"]) for i in ordered]
    return all(a is not None and b is not None and b > a for a, b in pairwise(values))


# --- R0: what ships today ----------------------------------------------------


def current(items: Items, *, min_numbers: int = 5) -> set[int]:
    """A right-aligned column of >= 5 bare integers, entirely left of the prose."""
    found: set[int] = set()
    for page, indices in by_page(items).items():
        edge = prose_edge(items, indices)
        if edge is None:
            continue
        for column in right_aligned_columns(items, numeric_indices(items, indices)):
            if len(column) >= min_numbers and items[column[0]]["r"] <= edge:
                found.update(column)
    return found


# --- R1: require the sequence to ascend --------------------------------------


def ascending(items: Items, *, min_numbers: int = 5) -> set[int]:
    """`current`, plus the column must be numbered down the page.

    Pure precision: it can only remove candidates `current` would have taken.
    Worth measuring on its own so the cost of the constraint is known before
    anything is relaxed in exchange for it.
    """
    found: set[int] = set()
    for page, indices in by_page(items).items():
        edge = prose_edge(items, indices)
        if edge is None:
            continue
        for column in right_aligned_columns(items, numeric_indices(items, indices)):
            if (
                len(column) >= min_numbers
                and items[column[0]]["r"] <= edge
                and ascends_down_the_page(items, column)
            ):
                found.update(column)
    return found


# --- R2: let the document vouch for its own margin ---------------------------


def cross_page(items: Items, *, min_numbers: int = 5, min_pages: int = 3, confirmed_min: int = 2) -> set[int]:
    """Find the margin's x-position from the pages that show it clearly, then
    apply it to the pages that do not.

    A pleading-paper margin is printed at the same place on every page. Where
    Docling absorbs line numbers into the text beside them, a page can be left
    with too few bare integers to clear the count threshold -- and the current
    rule then keeps the survivors in the body, which is precisely the residue
    that lands inside a citation.

    So: take the right edges of every column the strict test accepts, keep
    those recurring on at least `min_pages` pages, and on every other page
    accept a much shorter ascending column standing at the same edge.
    """
    pages = by_page(items)
    edges: dict[int, list[float]] = defaultdict(list)
    strict: set[int] = set()

    for page, indices in pages.items():
        edge = prose_edge(items, indices)
        if edge is None:
            continue
        for column in right_aligned_columns(items, numeric_indices(items, indices)):
            if len(column) >= min_numbers and items[column[0]]["r"] <= edge:
                strict.update(column)
                edges[round(items[column[0]]["r"] / ALIGNMENT_SLACK)].append(page)

    confirmed = {key for key, seen in edges.items() if len({*seen}) >= min_pages}
    if not confirmed:
        return strict

    found = set(strict)
    for page, indices in pages.items():
        for column in right_aligned_columns(items, numeric_indices(items, indices)):
            key = round(items[column[0]]["r"] / ALIGNMENT_SLACK)
            if key in confirmed and len(column) >= confirmed_min and ascends_down_the_page(items, column):
                found.update(column)
    return found


# --- R3: side-agnostic placement ---------------------------------------------


def either_margin(items: Items, *, min_numbers: int = 5) -> set[int]:
    """`ascending`, but the column may stand clear of the prose on either side.

    The current test is `column.r <= median prose left`, which can only see a
    left margin. Nothing about a line-number column requires it to be on the
    left, and a rule that names a jurisdiction's paper stock in its geometry is
    not general. This asks only that the column sit outside the prose block.
    """
    found: set[int] = set()
    for page, indices in by_page(items).items():
        prose = [i for i in indices if line_number_value(items[i]["text"]) is None]
        if not prose:
            continue
        left_edge = median(items[i]["l"] for i in prose)
        right_edge = median(items[i]["r"] for i in prose)
        for column in right_aligned_columns(items, numeric_indices(items, indices)):
            outside = items[column[0]]["r"] <= left_edge or items[column[0]]["l"] >= right_edge
            if len(column) >= min_numbers and outside and ascends_down_the_page(items, column):
                found.update(column)
    return found


# --- R4: tolerate a misread digit --------------------------------------------


def mostly_ascends(items: Items, column: list[int], *, share: float = 0.8) -> bool:
    """Whether most of the column is numbered down the page.

    Strict ascent is unusable on scanned filings. In document 013 the OCR reads
    the 9 of every margin as a 6, so all 28 numbers are present and in place and
    the sequence still reads `7, 8, 6, 10` -- one misread digit rejecting the
    whole page, on every page, and 660 numbers left in the body as a result.

    So the question is not whether the column ascends but whether it is
    *mostly* an ascending run: the longest increasing subsequence must cover
    `share` of it. A margin with a misread digit keeps 27 of 28. A column of
    arbitrary table values does not, and a column of repeated page numbers has
    a longest increasing subsequence of one.
    """
    ordered = sorted(column, key=lambda i: -items[i]["t"])
    values = [line_number_value(items[i]["text"]) or 0 for i in ordered]

    # Longest strictly increasing subsequence, O(n^2) on columns of ~28.
    best = [1] * len(values)
    for later in range(len(values)):
        for earlier in range(later):
            if values[earlier] < values[later]:
                best[later] = max(best[later], best[earlier] + 1)
    return bool(values) and max(best) >= share * len(values)


def tolerant(items: Items, *, min_numbers: int = 5) -> set[int]:
    """`current`, but the column must also be mostly numbered down the page."""
    found: set[int] = set()
    for page, indices in by_page(items).items():
        edge = prose_edge(items, indices)
        if edge is None:
            continue
        for column in right_aligned_columns(items, numeric_indices(items, indices)):
            if len(column) >= min_numbers and items[column[0]]["r"] <= edge and mostly_ascends(items, column):
                found.update(column)
    return found


# --- R5: side-agnostic, without any sequence test -----------------------------


def either_side_only(items: Items, *, min_numbers: int = 5) -> set[int]:
    """`current` with the position test widened to both margins, nothing else.

    Isolates the cost of dropping the left-hand assumption, which `either_margin`
    confounds with the sequence test.
    """
    found: set[int] = set()
    for page, indices in by_page(items).items():
        prose = [i for i in indices if line_number_value(items[i]["text"]) is None]
        if not prose:
            continue
        left_edge = median(items[i]["l"] for i in prose)
        right_edge = median(items[i]["r"] for i in prose)
        for column in right_aligned_columns(items, numeric_indices(items, indices)):
            outside = items[column[0]]["r"] <= left_edge or items[column[0]]["l"] >= right_edge
            if len(column) >= min_numbers and outside:
                found.update(column)
    return found


# --- R6: everything that survived --------------------------------------------


def combined(items: Items) -> set[int]:
    """Cross-page confirmation, tolerant sequence test, either margin."""
    found: set[int] = set()
    confirmed = cross_page(items)
    for page, indices in by_page(items).items():
        prose = [i for i in indices if line_number_value(items[i]["text"]) is None]
        if not prose:
            continue
        left_edge = median(items[i]["l"] for i in prose)
        right_edge = median(items[i]["r"] for i in prose)
        for column in right_aligned_columns(items, numeric_indices(items, indices)):
            outside = items[column[0]]["r"] <= left_edge or items[column[0]]["l"] >= right_edge
            if len(column) >= min_numbers_default and outside and mostly_ascends(items, column):
                found.update(column)
    return found | confirmed


min_numbers_default = 5


RULES = {
    "current": current,
    "ascending": ascending,
    "tolerant": tolerant,
    "cross_page": cross_page,
    "either_margin": either_margin,
    "either_side_only": either_side_only,
    "combined": combined,
}
