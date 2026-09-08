"""Inbound boundary for untrusted CourtListener docket-entry JSON."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mellea_lrc.courtlistener.docket_entry_models import (
    CourtListenerDocketEntries,
    CourtListenerDocketEntry,
)

_ID_IN_URL = re.compile(r"/(\d+)/?$")


class CourtListenerDocketEntryPayload(BaseModel):
    """One external docket-entry record."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    id: int | None = None
    docket: str | int | None = None
    entry_number: int | None = None
    date_filed: str | None = None
    description: str | None = None
    recap_documents: list[dict[str, Any]] = Field(default_factory=list)

    def to_domain(self) -> CourtListenerDocketEntry:
        """Convert one validated entry to the domain model."""
        return CourtListenerDocketEntry(
            entry_id=self.id,
            docket_id=_identifier(self.docket),
            entry_number=self.entry_number,
            date_filed=self.date_filed or None,
            description=self.description or None,
            document_ids=tuple(
                document["id"] for document in self.recap_documents if isinstance(document.get("id"), int)
            ),
        )


class CourtListenerDocketEntriesResponsePayload(BaseModel):
    """The external response from the docket-entries endpoint."""

    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    count: int | str | None = None
    results: list[CourtListenerDocketEntryPayload] = Field(default_factory=list)
    next: str | None = None

    def to_domain(self, *, docket_id: str) -> CourtListenerDocketEntries:
        """Convert the validated response to the domain model.

        ``count`` arrives as a URL rather than a number when the endpoint is
        asked without ``count=on``, so a value that is not a number is read as
        unknown rather than as zero.
        """
        return CourtListenerDocketEntries(
            docket_id=docket_id,
            count=self.count if isinstance(self.count, int) else None,
            entries=tuple(entry.to_domain() for entry in self.results),
            next_cursor=_cursor(self.next),
        )


def _identifier(value: str | int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return str(value)
    match = _ID_IN_URL.search(value)
    return match.group(1) if match else value or None


def _cursor(value: str | None) -> str | None:
    if not value or "cursor=" not in value:
        return None
    return value.split("cursor=", 1)[1].split("&", 1)[0] or None
