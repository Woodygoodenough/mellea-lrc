"""Docling-backed preprocessing from raw Layer 3 documents."""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING

from mellea_lrc.core.documents import SourceFormat, SourceMetadata
from mellea_lrc.preprocessing.margin_line_numbers import reclassify_margin_line_numbers
from mellea_lrc.preprocessing.repeated_furniture import reclassify_repeated_furniture
from mellea_lrc.preprocessing.types import (
    DEFAULT_LAYOUT_RULES,
    LayoutRule,
    PreprocessedDocument,
    PreprocessingBackend,
    PreprocessingMetadata,
)

if TYPE_CHECKING:
    from docling_core.types.doc.document import DoclingDocument

_SOURCE_FORMAT_BY_SUFFIX = {
    ".pdf": SourceFormat.PDF,
    ".docx": SourceFormat.DOCX,
    ".pptx": SourceFormat.PPTX,
    ".xlsx": SourceFormat.XLSX,
    ".html": SourceFormat.HTML,
    ".htm": SourceFormat.HTML,
    ".md": SourceFormat.MARKDOWN,
}


def is_docling_supported_format(path: Path | str) -> bool:
    """Return True when Docling supports the path suffix."""
    return Path(path).suffix.lower() in _SOURCE_FORMAT_BY_SUFFIX


def _docling_version() -> str | None:
    try:
        return version("docling")
    except PackageNotFoundError:
        return None


def _source_format(path: Path) -> SourceFormat:
    return _SOURCE_FORMAT_BY_SUFFIX.get(path.suffix.lower(), SourceFormat.UNKNOWN)


def _apply_layout_rules(
    document: DoclingDocument, rules: Sequence[LayoutRule]
) -> tuple[tuple[LayoutRule, int], ...]:
    """Run each rule against the document, in the order given.

    Returns how many items each one moved out of the body, which is what the
    result records: a rule that ran and removed nothing is not the same as a
    rule that never ran.
    """
    removals = []
    for rule in rules:
        if rule is LayoutRule.MARGIN_LINE_NUMBERS:
            removed = reclassify_margin_line_numbers(document)
        elif rule is LayoutRule.REPEATED_FURNITURE:
            removed = reclassify_repeated_furniture(document)
        else:
            msg = f"Unknown layout rule: {rule}"
            raise ValueError(msg)
        removals.append((rule, removed))
    return tuple(removals)


def preprocess_with_docling(
    path: Path | str,
    *,
    layout_rules: Sequence[LayoutRule] = DEFAULT_LAYOUT_RULES,
) -> PreprocessedDocument:
    """Convert a raw document to plain text using Docling.

    ``layout_rules`` says which page furniture to take out before the text is
    written. Docling reads all of it correctly and files some of it under the
    body layer, where it survives into the text and lands wherever the page
    broke -- a column of margin integers inside a citation, a running head
    between a reporter and its page.

    Both run by default. None of it is the document's text, and a rendering that
    interleaves it into a citation is wrong about the document. Pass a shorter
    list to keep some of it, or an empty one to keep all of it.

    Each rule moves the offsets of everything after it, so two renderings made
    under different lists are different coordinate spaces. Which ran is recorded
    on the result rather than assumed.
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        msg = (
            "Docling is required for raw document preprocessing. Install with: uv sync --group preprocessing"
        )
        raise ImportError(msg) from exc

    source_path = Path(path)
    converter = DocumentConverter()
    result = converter.convert(str(source_path))
    applied = tuple(layout_rules)
    removals = _apply_layout_rules(result.document, applied)
    text = result.document.export_to_text()  # Ensure to normalize all characters to Unicode TODO

    return PreprocessedDocument(
        source_metadata=SourceMetadata(
            path=str(source_path),
            format=_source_format(source_path),
        ),
        text=text,
        preprocessing_metadata=PreprocessingMetadata(
            backend=PreprocessingBackend.DOCLING,
            backend_version=_docling_version(),
            layout_rules=applied,
            layout_removals=removals,
        ),
    )
