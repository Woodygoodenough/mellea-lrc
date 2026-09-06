"""Preprocessing layer public API."""

from mellea_lrc.core.documents import DocumentBase, SourceFormat, SourceMetadata
from mellea_lrc.preprocessing.docket_stamp import (
    docket_stamps,
    looks_like_a_stamp,
    reclassify_docket_stamps,
)
from mellea_lrc.preprocessing.docling import is_docling_supported_format, preprocess_with_docling
from mellea_lrc.preprocessing.document_index import index_table_spans, is_within
from mellea_lrc.preprocessing.margin_line_numbers import (
    margin_line_numbers,
    reclassify_margin_line_numbers,
)
from mellea_lrc.preprocessing.pipeline import preprocess
from mellea_lrc.preprocessing.plain_text import preprocess_plain_text_from_string
from mellea_lrc.preprocessing.repeated_furniture import (
    reclassify_repeated_furniture,
    repeated_furniture,
)
from mellea_lrc.preprocessing.types import (
    DEFAULT_LAYOUT_RULES,
    LayoutRule,
    PreprocessedDocument,
    PreprocessingBackend,
    PreprocessingMetadata,
)

__all__ = [
    "DEFAULT_LAYOUT_RULES",
    "DocumentBase",
    "LayoutRule",
    "PreprocessedDocument",
    "PreprocessingBackend",
    "PreprocessingMetadata",
    "SourceFormat",
    "SourceMetadata",
    "docket_stamps",
    "index_table_spans",
    "is_docling_supported_format",
    "is_within",
    "looks_like_a_stamp",
    "margin_line_numbers",
    "preprocess",
    "preprocess_plain_text_from_string",
    "preprocess_with_docling",
    "reclassify_docket_stamps",
    "reclassify_margin_line_numbers",
    "reclassify_repeated_furniture",
    "repeated_furniture",
]
