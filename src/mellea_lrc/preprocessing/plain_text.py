"""Load plain text files into canonical preprocessing types.

A text file is its text. Nothing is stripped from the front of it, so an offset
into the file is an offset into the document, and there is one coordinate system
rather than one per source.

This project used to write conversion provenance -- the source PDF, the Docling
version -- as a header above a `--- Plain text ---` marker, and every reader had
to know to skip it. Court records arrive with enough furniture of their own; the
provenance now sits beside the text in a `renderings.json` or `documents.json`,
where reading it is a choice rather than an obligation.
"""

from pathlib import Path

from mellea_lrc.core.documents import SourceFormat, SourceMetadata
from mellea_lrc.preprocessing.types import (
    PreprocessedDocument,
    PreprocessingBackend,
    PreprocessingMetadata,
)


def preprocess_plain_text(path: Path | str) -> PreprocessedDocument:
    """Load a `.txt` file as a preprocessed document."""
    source_path = Path(path)
    return PreprocessedDocument(
        source_metadata=SourceMetadata(
            path=str(source_path),
            format=SourceFormat.TEXT,
        ),
        text=source_path.read_text(encoding="utf-8"),
        preprocessing_metadata=PreprocessingMetadata(
            backend=PreprocessingBackend.PLAIN_TEXT,
        ),
    )


def preprocess_plain_text_from_string(
    text: str,
    *,
    source_path: str | None = None,
) -> PreprocessedDocument:
    """Wrap raw text in a preprocessed document without reading a file."""
    return PreprocessedDocument(
        source_metadata=SourceMetadata(
            path=source_path,
            format=SourceFormat.TEXT,
        ),
        text=text,
        preprocessing_metadata=PreprocessingMetadata(
            backend=PreprocessingBackend.PLAIN_TEXT,
        ),
    )
