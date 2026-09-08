"""Reusable CourtListener API client and retrieval capabilities."""

from mellea_lrc.courtlistener.citation_lookup import normalize_citation_lookup_payload
from mellea_lrc.courtlistener.citation_lookup_models import (
    CourtListenerCitationLookup,
)
from mellea_lrc.courtlistener.client import (
    CourtListenerClient,
    CourtListenerConfig,
    CourtListenerError,
)
from mellea_lrc.courtlistener.docket_entry_models import (
    CourtListenerDocketEntries,
    CourtListenerDocketEntry,
)
from mellea_lrc.courtlistener.docket_models import CourtListenerDocket, courtlistener_docket_url
from mellea_lrc.courtlistener.opinion_models import (
    CourtListenerClusterDetail,
    CourtListenerOpinion,
    CourtListenerOpinionCluster,
    CourtListenerOpinionClusterCitation,
)
from mellea_lrc.courtlistener.protocols import CourtListenerServiceClient
from mellea_lrc.courtlistener.recap_document_models import CourtListenerRecapDocument
from mellea_lrc.courtlistener.search_models import CourtListenerSearchResult

__all__ = [
    "CourtListenerCitationLookup",
    "CourtListenerClient",
    "CourtListenerClusterDetail",
    "CourtListenerConfig",
    "CourtListenerDocket",
    "CourtListenerDocketEntries",
    "CourtListenerDocketEntry",
    "CourtListenerError",
    "CourtListenerOpinion",
    "CourtListenerOpinionCluster",
    "CourtListenerOpinionClusterCitation",
    "CourtListenerRecapDocument",
    "CourtListenerSearchResult",
    "CourtListenerServiceClient",
    "courtlistener_docket_url",
    "normalize_citation_lookup_payload",
]
