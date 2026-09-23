"""Source-grounded, citation-local field readings."""

from __future__ import annotations

from typing import Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from mellea_lrc.model.span import Span

T = TypeVar("T")


def source_quote(source: str, span: Span) -> str:
    """Return an exact nonempty slice or fail at the quoting boundary."""
    if span.start == span.end or span.end > len(source):
        raise ValueError("Field span is outside the source or empty")
    quote = source[span.start : span.end]
    if not quote.strip():
        raise ValueError("Field quote is blank")
    return quote


class CitationField(BaseModel, Generic[T]):
    """A field reading and the node that made it; subclasses own normalization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    normalized: T
    quote: str | None = None
    span: Span | None = None

    @model_validator(mode="after")
    def _validate_reading(self) -> Self:
        if self.normalized is None or (isinstance(self.normalized, str) and not self.normalized.strip()):
            raise ValueError("Parsed field has no normalized value")
        if (self.quote is None) != (self.span is None):
            raise ValueError("Quote and span must be present together")
        if self.quote is not None and not self.quote.strip():
            raise ValueError("Field quote is blank")
        return self

    def validate_source(self, source: str) -> None:
        """Recheck exact source grounding after loading a document."""
        if self.span is not None and source_quote(source, self.span) != self.quote:
            raise ValueError("Field quote does not match its source span")
