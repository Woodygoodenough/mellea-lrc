"""Domain model for one document filed on a docket, as the archive holds it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CourtListenerRecapDocument:
    """One filed document: how the clerk described it, and its text where the archive has it.

    ``plain_text`` is the archive's own transcription, which exists only where
    somebody bought the document from PACER and it was uploaded. An entry with
    no text is not a missing document; it is a document nobody has paid for.
    """

    document_id: str
    description: str | None = None
    document_type: str | None = None
    page_count: int | None = None
    is_available: bool = False
    plain_text: str = ""
    filepath: str | None = None
    """Where the archive stores the file, under ``storage.courtlistener.com``."""
