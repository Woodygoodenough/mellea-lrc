"""Inbound boundary for untrusted CourtListener RECAP-document JSON."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from mellea_lrc.courtlistener.recap_document_models import CourtListenerRecapDocument


class CourtListenerRecapDocumentPayload(BaseModel):
    """The external record for one document on a docket."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    id: int | str
    description: str | None = None
    document_type: int | str | None = None
    page_count: int | None = None
    is_available: bool | None = None
    plain_text: str | None = None
    filepath_local: str | None = None

    def to_domain(self) -> CourtListenerRecapDocument:
        """Convert the validated record to the domain model."""
        return CourtListenerRecapDocument(
            document_id=str(self.id),
            description=self.description or None,
            document_type=str(self.document_type) if self.document_type is not None else None,
            page_count=self.page_count,
            is_available=bool(self.is_available),
            plain_text=self.plain_text or "",
            filepath=self.filepath_local or None,
        )
