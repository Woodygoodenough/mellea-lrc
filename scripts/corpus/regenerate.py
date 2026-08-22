"""Regenerate false-citation-bench from its PDFs, and carry the gold spans over.

The shipped corpus is a Docling rendering of the filings, and its annotations
are offsets into that rendering. That makes the rendering part of the dataset's
contract, and changing it a deliberate act rather than an incidental one.

There is a reason to change it. Docling reads the numbered left margin of
pleading paper correctly but files it under the `body` content layer, so it
survives into the text and lands wherever the page happened to break -- in
eight of the twenty-six filings, 4,854 numbers, sometimes in the middle of a
citation. The corpus documents three citations excluded for not being "stated
completely in one run", and two of them are stated completely in the filing and
broken only by the rendering.

This script produces the corrected rendering and re-derives every gold span
against it, by aligning old text to new and projecting each span through the
blocks the two share. A span that lands in a changed region is reported rather
than guessed at.

Two things move the text, and they have to be told apart, so each filing is
rendered twice -- once with the margin rule and once without -- and both are
aligned against the shipped text:

    failures under both      the Docling version differs from the shipped one
    failures under one only  attributable to the margin rule

On the corpus as of Docling 2.115 the second number is **zero**: 574 of 594
spans carry over exactly, and all 20 that do not are table-of-authorities cells
that move because table structure inference differs between Docling versions.
Removing 4,854 margin items costs no gold span at all.

That is also the argument for pinning the version alongside the corpus. The
margin rule reads text-item geometry, which is stable; table parsing is not.

Usage::

    uv run python -m scripts.corpus.regenerate \
        --benchmark data/false-citation-bench \
        --output data/false-citation-bench-v2
"""

from __future__ import annotations

import argparse
import bisect
import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING

from mellea_lrc.preprocessing.margin_line_numbers import reclassify_margin_line_numbers

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

# The shipped text files carry a RECAP header above the rendering.
BODY_SEPARATOR = "--- Plain text ---\n"


@dataclass(frozen=True, slots=True)
class Alignment:
    """A projection from offsets in one rendering to offsets in another."""

    blocks: tuple[tuple[int, int, int], ...]
    starts: tuple[int, ...]

    @classmethod
    def between(cls, before: str, after: str) -> Alignment:
        """Align two renderings of the same document."""
        matching = SequenceMatcher(None, before, after, autojunk=False).get_matching_blocks()
        blocks = tuple((b.a, b.b, b.size) for b in matching if b.size)
        return cls(blocks=blocks, starts=tuple(b[0] for b in blocks))

    def project(self, index: int) -> int | None:
        """Map one offset, or return None if it fell inside a changed region."""
        position = bisect.bisect_right(self.starts, index) - 1
        if position < 0:
            return None
        start, target, size = self.blocks[position]
        return target + (index - start) if index < start + size else None

    def project_span(self, start: int, end: int) -> tuple[int, int] | None:
        """Map a half-open span, requiring both ends to survive."""
        first, last = self.project(start), self.project(end - 1)
        return None if first is None or last is None else (first, last + 1)


@dataclass(frozen=True, slots=True)
class DocumentResult:
    """What became of one filing's text and its annotations."""

    stem: str
    margin_items: int
    carried: tuple[dict, ...]
    drift_failures: int
    total_failures: int

    @property
    def margin_failures(self) -> int:
        """Spans lost to the margin rule rather than to the Docling version."""
        return self.total_failures - self.drift_failures


def _render(pdf: Path) -> tuple[str, str, int]:
    """Return this filing rendered without and with the margin rule, and the count."""
    from docling.document_converter import DocumentConverter

    document = DocumentConverter().convert(str(pdf)).document
    control = document.export_to_text()
    margin_items = reclassify_margin_line_numbers(document)
    return control, document.export_to_text(), margin_items


def _shipped_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    return raw.split(BODY_SEPARATOR, 1)[1] if BODY_SEPARATOR in raw else raw


def _carry_over(shipped: str, rendering: str, annotations: Sequence[dict]) -> tuple[list[dict], int]:
    """Project each annotation onto a rendering, counting those that cannot be."""
    alignment = Alignment.between(shipped, rendering)
    carried, failures = [], 0
    for record in annotations:
        moved = alignment.project_span(record["span"]["start"], record["span"]["end"])
        if moved is None or rendering[moved[0] : moved[1]] != record["matched_text"]:
            failures += 1
            continue
        start, end = moved
        carried.append(
            {
                **record,
                "span": {"start": start, "end": end},
                "id": f"{record['id'].split(':')[0]}:{start}-{end}",
            }
        )
    return carried, failures


def regenerate(benchmark: Path, output: Path) -> list[DocumentResult]:
    """Re-render every filing without its margin and carry the gold spans over."""
    annotations = _annotations_by_document(benchmark / "derived" / "extraction.jsonl")
    (output / "documents_txt").mkdir(parents=True, exist_ok=True)

    results = []
    for pdf in sorted((benchmark / "documents_pdf").glob("*.pdf")):
        name = _text_name(benchmark, pdf)
        shipped = _shipped_text(benchmark / "documents_txt" / name)
        control, trimmed, margin_items = _render(pdf)
        (output / "documents_txt" / name).write_text(trimmed, encoding="utf-8")

        _, drift = _carry_over(shipped, control, annotations.get(name, ()))
        carried, total = _carry_over(shipped, trimmed, annotations.get(name, ()))
        results.append(
            DocumentResult(
                stem=pdf.stem[:3],
                margin_items=margin_items,
                carried=tuple(carried),
                drift_failures=drift,
                total_failures=total,
            )
        )
        print(
            f"{pdf.stem[:3]}  margin={margin_items:5}  carried={len(carried):3}"
            f"  drift_fail={drift:3}  total_fail={total:3}",
            flush=True,
        )

    _write_annotations(output / "derived" / "extraction.jsonl", results)
    return results


def _annotations_by_document(path: Path) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for record in _read_jsonl(path):
        grouped.setdefault(record["document"], []).append(record)
    return grouped


def _read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _text_name(benchmark: Path, pdf: Path) -> str:
    """The text file corresponding to a PDF, matched on the numeric prefix."""
    matches = sorted((benchmark / "documents_txt").glob(f"{pdf.stem[:3]}*.txt"))
    if not matches:
        msg = f"no text file for {pdf.name}"
        raise FileNotFoundError(msg)
    return matches[0].name


def _write_annotations(path: Path, results: Sequence[DocumentResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record) for result in results for record in result.carried]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """Regenerate the corpus and report what carried over."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    results = regenerate(arguments.benchmark, arguments.output)
    carried = sum(len(r.carried) for r in results)
    drift = sum(r.drift_failures for r in results)
    total = sum(r.total_failures for r in results)
    margin_items = sum(r.margin_items for r in results)
    print(
        f"\nmargin items removed: {margin_items}"
        f"\nspans carried over  : {carried}"
        f"\nlost to version drift: {drift}"
        f"\nlost to the margin rule: {total - drift}"
    )


if __name__ == "__main__":
    main()
