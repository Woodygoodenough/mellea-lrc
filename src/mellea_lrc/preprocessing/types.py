"""Formal types for Layer 2 preprocessed documents."""

from dataclasses import dataclass
from enum import Enum

from mellea_lrc.core.documents import DocumentBase
from mellea_lrc.core.spans import Span


class PreprocessingBackend(str, Enum):
    """Engine that produced the preprocessed text."""

    DOCLING = "docling"
    PLAIN_TEXT = "plain_text"


class LayoutRule(str, Enum):
    """A thing printed on the page that is not part of the document's text.

    Each names furniture a court or a word processor added around the writing:
    the numbered margin of pleading paper, a running head, the stamp an ECF
    system prints when a document is filed. Every one of them changes the text
    and therefore every offset after it, so which ran is recorded beside the
    text rather than assumed.
    """

    MARGIN_LINE_NUMBERS = "margin_line_numbers"
    """The numbered left margin of pleading paper."""

    REPEATED_FURNITURE = "repeated_furniture"
    """Running heads and feet the converter labelled inconsistently."""

    DOCKET_STAMP = "docket_stamp"
    """The filing stamp a court prints across the top of every page."""


DEFAULT_LAYOUT_RULES: tuple[LayoutRule, ...] = (
    LayoutRule.MARGIN_LINE_NUMBERS,
    LayoutRule.REPEATED_FURNITURE,
    LayoutRule.DOCKET_STAMP,
)
"""All of them. None of this is the document's text, and a rendering that keeps
it is wrong about the document -- a margin number landing inside a citation, a
page stamp read as part of a date. Pass a shorter list to keep some of it."""


@dataclass(frozen=True, slots=True)
class PreprocessingMetadata:
    """Backend provenance for the preprocessing stage."""

    backend: PreprocessingBackend = PreprocessingBackend.PLAIN_TEXT
    backend_version: str | None = None
    layout_rules: tuple[LayoutRule, ...] = ()
    """Which rules ran, in the order they ran.

    Empty means none did, which is not the same as a rule finding nothing: the
    two produce different text and therefore different offsets, so a document
    has to record which reading it was rendered under.
    """

    layout_removals: tuple[tuple[LayoutRule, int], ...] = ()
    """How many items each rule moved out of the body."""


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
