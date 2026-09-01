"""Formal types for Layer 2 preprocessed documents."""

from dataclasses import dataclass
from enum import Enum

from mellea_lrc.core.documents import DocumentBase
from mellea_lrc.core.spans import Span


class PreprocessingBackend(str, Enum):
    """Engine that produced the preprocessed text."""

    DOCLING = "docling"
    PLAIN_TEXT = "plain_text"


@dataclass(frozen=True, slots=True)
class PreprocessingMetadata:
    """Backend provenance for the preprocessing stage."""

    backend: PreprocessingBackend = PreprocessingBackend.PLAIN_TEXT
    backend_version: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PreprocessedDocument(DocumentBase):
    """Layer 2 text output consumed by citation extraction."""

    text: str
    preprocessing_metadata: PreprocessingMetadata
    index_spans: tuple[Span, ...] = ()
    """Regions of `text` holding a table of authorities, which cites nothing.

    An index entry lists a case; it attaches no proposition to it and makes no
    claim about any page. Empty when the backend cannot tell -- plain text
    carries no structure, so absence here means unknown rather than none.
    """

    def __post_init__(self) -> None:
        if not self.text:
            msg = "PreprocessedDocument.text must not be empty"
            raise ValueError(msg)
