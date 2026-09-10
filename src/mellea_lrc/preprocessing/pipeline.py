"""Preprocessing pipeline from Layer 3 raw documents to Layer 2 text."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mellea_lrc.preprocessing.docling import is_docling_supported_format, preprocess_with_docling
from mellea_lrc.preprocessing.plain_text import preprocess_plain_text
from mellea_lrc.preprocessing.types import DEFAULT_LAYOUT_RULES, LayoutRule, PreprocessedDocument


def preprocess(
    path: Path | str,
    *,
    layout_rules: Sequence[LayoutRule] = DEFAULT_LAYOUT_RULES,
) -> PreprocessedDocument:
    """Preprocess a document using the backend appropriate for its format.

    One list of rules serves both backends: each applies the ones its input can
    carry, and the result records what ran. A caller that wants a rendering with
    nothing taken out passes an empty list, whatever the format.
    """
    source_path = Path(path)
    if source_path.suffix.lower() == ".txt":
        return preprocess_plain_text(source_path, layout_rules=layout_rules)
    if not is_docling_supported_format(source_path):
        msg = f"Unsupported document format: {source_path.suffix or '<none>'}"
        raise ValueError(msg)
    return preprocess_with_docling(source_path, layout_rules=layout_rules)
