"""Which documents the overreach proxy flags, and whether it is right to.

The proxy calls an item overreach when it was removed while not sitting in a
run of four or more ascending numbers *among the removed items on its page*.
That is deliberately harsh: a page whose margin Docling only partly separated
leaves a short run, and the proxy cannot tell that from a numbered list wrongly
taken. This prints the context so the difference can be read.

    uv run python -m exploration.margin_rules.overreach_probe
"""

from __future__ import annotations

import json
from pathlib import Path

from exploration.margin_rules.candidates import RULES

RULE = "current"


def main() -> None:
    scores = json.loads(Path("data/margin-rule-scores.json").read_text())
    corpus = {
        entry["source"]: entry["items"]
        for entry in json.loads(Path("data/page-layout-cache.json").read_text())
    }

    for source, row in scores[RULE].items():
        if not row["loose"]:
            continue
        print(f"--- {source[:60]} : {row['loose']} ---")
        items = corpus[source]
        removed = RULES[RULE](items)
        pages = sorted({items[i]["page"] for i in removed})
        for page in pages:
            on_page = sorted(
                (i for i in removed if items[i]["page"] == page),
                key=lambda i: -items[i]["t"],
            )
            if len(on_page) > 6:
                continue
            print(f"  page {page}: removed {[items[i]['text'] for i in on_page]}")
            print(f"    right edges {[round(items[i]['r'], 1) for i in on_page]}")
            others = [
                items[i]["text"][:40]
                for i in range(len(items))
                if items[i]["page"] == page and i not in removed and items[i]["text"].strip()
            ]
            print(f"    kept on that page: {others[:5]}")


if __name__ == "__main__":
    main()
