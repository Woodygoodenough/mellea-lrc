"""RECAP-document retrieval and domain conversion."""

from mellea_lrc.courtlistener.recap_document_models import CourtListenerRecapDocument
from mellea_lrc.courtlistener.recap_document_transport import CourtListenerRecapDocumentPayload


def normalize_recap_document_payload(payload: object) -> CourtListenerRecapDocument:
    """Validate one external RECAP-document payload and convert it to the domain model."""
    return CourtListenerRecapDocumentPayload.model_validate(payload).to_domain()
