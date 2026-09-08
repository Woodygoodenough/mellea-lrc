"""Docket-entry retrieval and domain conversion."""

from mellea_lrc.courtlistener.docket_entry_models import CourtListenerDocketEntries
from mellea_lrc.courtlistener.docket_entry_transport import CourtListenerDocketEntriesResponsePayload


def normalize_docket_entries_payload(payload: object, *, docket_id: str) -> CourtListenerDocketEntries:
    """Validate an external docket-entries payload and convert it to the domain model."""
    return CourtListenerDocketEntriesResponsePayload.model_validate(payload).to_domain(docket_id=docket_id)
