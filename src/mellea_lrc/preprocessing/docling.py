"""Docling-backed preprocessing from raw Layer 3 documents."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from mellea_lrc.core.documents import SourceFormat, SourceMetadata
from mellea_lrc.preprocessing.margin_line_numbers import reclassify_margin_line_numbers
from mellea_lrc.preprocessing.types import (
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


def preprocess_with_docling(
    path: Path | str,
    *,
    drop_margin_line_numbers: bool = False,
) -> PreprocessedDocument:
    """Convert a raw document to plain text using Docling.

    Set ``drop_margin_line_numbers`` to remove the numbered left margin of
    pleading paper before the text is written out. Docling reads that margin
    correctly but files it under the body layer, so it otherwise survives into
    the text as a column of integers landing wherever the page broke -- often
    inside a citation. See :mod:`mellea_lrc.preprocessing.margin_line_numbers`.

    This is off by default because it moves offsets. Text rendered with it is a
    different coordinate space from text rendered without it, and spans
    measured against one do not address the other.
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
    dropped = reclassify_margin_line_numbers(result.document) if drop_margin_line_numbers else None
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
            margin_line_numbers_dropped=dropped,
        ),
    )
