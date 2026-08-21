"""Run the identity-layer probe over a LePhantomCite split and write the result.

    uv run --env-file .env python -m evaluations.lephantomcite.run_locator_probe \
      --dataset <dir>/eval.jsonl --output locator-probe.json

The output is one JSON object: the per-citation outcomes, and a cross-tabulation
of outcome against the benchmark's own labels. No model is called.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from evaluations.lephantomcite.dataset import iter_labelled_citations, load_excerpts
from evaluations.lephantomcite.locator_probe import DEFAULT_MAX_WORKERS, probe_locators, summarize

logger = logging.getLogger(__name__)


def main() -> None:
    """Probe every citation in the split and write outcomes plus a cross-tabulation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="path to eval.jsonl")
    parser.add_argument("--output", type=Path, required=True, help="path to write the result JSON")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    excerpts = load_excerpts(args.dataset)
    pairs = list(iter_labelled_citations(excerpts))
    texts = [citation.cited_text for _, citation in pairs]
    logger.info(
        "probing %d citations (%d distinct) from %d excerpts", len(texts), len(set(texts)), len(excerpts)
    )

    results = probe_locators(texts, max_workers=args.max_workers)

    by_label: dict[str, Counter[str]] = {}
    records = []
    for excerpt, citation in pairs:
        result = results[citation.cited_text]
        label = "|".join(sorted(kind.value for kind in citation.types)) or "sound"
        by_label.setdefault(label, Counter())[result.outcome.value] += 1
        records.append(
            {
                "excerpt_id": excerpt.excerpt_id,
                "cited_text": citation.cited_text,
                "label": label,
                "outcome": result.outcome.value,
                "cluster_count": result.cluster_count,
                "detail": result.detail,
            }
        )

    payload = {
        "citations": len(records),
        "distinct_citations": len(set(texts)),
        "excerpts": len(excerpts),
        "totals": summarize([results[text] for text in texts]),
        "by_label": {label: dict(counts) for label, counts in sorted(by_label.items())},
        "records": records,
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("wrote %s", args.output)


if __name__ == "__main__":
    main()
