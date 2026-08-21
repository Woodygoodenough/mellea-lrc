"""Run the full validation pipeline over LePhantomCite excerpts.

    uv run --env-file .env python -m evaluations.lephantomcite.run_validation \
      --dataset <dir>/eval.jsonl --output-dir run-lephantomcite --label wrong_pincite

Each excerpt is treated as a document: extracted, validated, and written out as
its own serialized `ValidatedDocument`, so a run can be resumed and a trace can
be read back per excerpt. Selecting a label runs only the excerpts carrying it,
which is how a single defect category is measured without paying for the rest.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from evaluations.lephantomcite.dataset import Excerpt, HallucinationType, load_excerpts
from mellea_lrc.extraction import extract_from_plain_text
from mellea_lrc.serialization import serialize_validated_document
from mellea_lrc.validation import validate_document

logger = logging.getLogger(__name__)


def select(excerpts: tuple[Excerpt, ...], label: str | None, limit: int | None) -> list[Excerpt]:
    """Keep the excerpts carrying `label`, or all of them when no label is given."""
    if label is None:
        chosen = list(excerpts)
    else:
        kind = HallucinationType(label)
        chosen = [
            excerpt for excerpt in excerpts if any(kind in citation.types for citation in excerpt.citations)
        ]
    return chosen[:limit] if limit is not None else chosen


def output_name(excerpt: Excerpt) -> str:
    """A filesystem-safe name that stays stable across runs of the same excerpt."""
    return excerpt.excerpt_id.replace("/", "_").replace(":", "__") + ".json"


async def run(args: argparse.Namespace) -> None:
    """Validate each selected excerpt and write one serialized document per excerpt."""
    excerpts = load_excerpts(args.dataset)
    chosen = select(excerpts, args.label, args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("validating %d of %d excerpts", len(chosen), len(excerpts))

    for index, excerpt in enumerate(chosen, start=1):
        destination = args.output_dir / output_name(excerpt)
        if destination.exists() and not args.overwrite:
            logger.info("[%d/%d] skipping %s (already written)", index, len(chosen), excerpt.excerpt_id)
            continue
        logger.info("[%d/%d] %s", index, len(chosen), excerpt.excerpt_id)
        try:
            document = extract_from_plain_text(excerpt.text)
            validated = await validate_document(document)
        except Exception:
            logger.exception("failed on %s", excerpt.excerpt_id)
            continue
        payload = {
            "excerpt_id": excerpt.excerpt_id,
            "filename": excerpt.filename,
            "labels": {
                citation.cited_text: sorted(kind.value for kind in citation.types)
                for citation in excerpt.citations
                if citation.types
            },
            "validated": serialize_validated_document(validated),
        }
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    """Parse arguments and run the validation sweep."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--label",
        choices=[kind.value for kind in HallucinationType],
        help="run only excerpts carrying this defect type",
    )
    parser.add_argument("--limit", type=int, help="stop after this many excerpts")
    parser.add_argument("--overwrite", action="store_true", help="revalidate excerpts already written")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
