"""Why does requiring an ascending column cost 660 removals in document 013?

The constraint looks free -- a margin is numbered down the page, so demanding
that its values ascend should reject nothing real. It rejects a great deal, and
this prints the columns it throws away so the reason is visible rather than
guessed at.

    uv run python -m exploration.margin_rules.diagnose
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

from exploration.margin_rules.candidates import (
    by_page,
    line_number_value,
    numeric_indices,
    prose_edge,
    right_aligned_columns,
)

DOCUMENT = "013__gunter-v-contango-ore-inc-et-al__complaint"


def main() -> None:
    corpus = json.loads(Path("data/page-layout-cache.json").read_text())
    entry = next(e for e in corpus if e["source"] == DOCUMENT)
    items = entry["items"]

    rejected = kept = 0
    shown = 0
    for page, indices in sorted(by_page(items).items()):
        edge = prose_edge(items, indices)
        if edge is None:
            continue
        for column in right_aligned_columns(items, numeric_indices(items, indices)):
            if len(column) < 5 or items[column[0]]["r"] > edge:
                continue
            ordered = sorted(column, key=lambda i: -items[i]["t"])
            values = [line_number_value(items[i]["text"]) for i in ordered]
            ascending = all(b > a for a, b in pairwise(values))
            if ascending:
                kept += 1
                continue
            rejected += 1
            if shown < 6:
                shown += 1
                print(f"page {page}: {len(column)} items, right edge {items[column[0]]['r']:.1f}")
                print(f"  values top to bottom: {values}")
                tops = [round(items[i]["t"], 1) for i in ordered]
                print(f"  top edges:            {tops}")
                print()

    print(f"columns accepted by position+count: {kept + rejected}")
    print(f"  of those, ascending:  {kept}")
    print(f"  of those, rejected:   {rejected}")


if __name__ == "__main__":
    main()
