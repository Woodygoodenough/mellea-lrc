"""Docling-backed preprocessing from raw Layer 3 documents."""

from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from mellea_lrc.core.documents import SourceFormat, SourceMetadata
from mellea_lrc.preprocessing.docket_stamp import reclassify_docket_stamps
from mellea_lrc.preprocessing.document_index import index_table_spans
from mellea_lrc.preprocessing.margin_line_numbers import reclassify_margin_line_numbers
from mellea_lrc.preprocessing.repeated_furniture import reclassify_repeated_furniture
from mellea_lrc.preprocessing.types import (
    DEFAULT_LAYOUT_RULES,
    LayoutRule,
    PreprocessedDocument,
    PreprocessingBackend,
    PreprocessingMetadata,
)

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


_LAYOUT_RULES = {
    LayoutRule.MARGIN_LINE_NUMBERS: reclassify_margin_line_numbers,
    LayoutRule.REPEATED_FURNITURE: reclassify_repeated_furniture,
    LayoutRule.DOCKET_STAMP: reclassify_docket_stamps,
}


def preprocess_with_docling(
    path: Path | str,
    *,
    layout_rules: Sequence[LayoutRule] = DEFAULT_LAYOUT_RULES,
) -> PreprocessedDocument:
    """Convert a raw document to plain text using Docling.

    ``layout_rules`` says which page furniture to take out before the text is
    written. Docling reads all of it correctly and files some of it under the
    body layer, where it survives into the text and lands wherever the page
    broke -- a margin number inside a citation, the `9` of "Page 3 of 9" read
    together with the date after it.

    All three run by default. None of it is the document's text, and a rendering
    that interleaves it into a citation is wrong about the document. Pass a
    shorter list to keep some of it, or an empty one to keep all of it.

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
    removals = tuple((rule, _LAYOUT_RULES[rule](result.document)) for rule in applied)
    text = result.document.export_to_text()  # Ensure to normalize all characters to Unicode TODO
    index_spans = index_table_spans(result.document)

    return PreprocessedDocument(
        source_metadata=SourceMetadata(
            path=str(source_path),
            format=_source_format(source_path),
        ),
        text=text,
        index_spans=index_spans,
        preprocessing_metadata=PreprocessingMetadata(
            backend=PreprocessingBackend.DOCLING,
            backend_version=_docling_version(),
            layout_rules=applied,
            layout_removals=removals,
        ),
    )
