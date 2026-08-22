"""Find filings that contain fabricated citations, without anyone's list.

The corpus this project needs is filings whose citations a court found
defective. The obvious way to build one is to work down a published tracker of
AI-fabrication cases, and that is worth doing -- but it is someone else's list,
it covers the whole world while our reach is US federal courts through RECAP,
and using it is not a method anyone can reproduce or extend.

This does it from CourtListener's own search instead, so the corpus is
reproducible from a public API and the search itself is the contribution. The
tracker then becomes a way to check how much this found, rather than the source.

**The document we want is not the one the search finds.** A judge's order says
the citations were fabricated; the fabrication is in the brief the order is
about. An opponent's response says the same thing about the same brief. Either
way the search hits the document that *complains*, and the one worth collecting
is a different entry on the same docket.

So discovery has two halves, and only the first is easy:

1. **Find the complaint about the citations.** Exact phrases work, loose terms
   do not: `"fabricated citations"` matches 141 RECAP documents, while the
   unquoted words match 17,007, because almost every brief contains both.
2. **Resolve to the filing being complained about.** The order usually quotes
   the citation it is rejecting, and that quotation is the evidence -- whichever
   document on the docket contains that citation is the one. That is checkable
   rather than inferred, which is what makes it worth building.

This module is the first half.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

# Phrases a court or an opponent uses when rejecting a citation. Each must be
# exact: CourtListener treats bare words as a loose match, so `hallucinated
# citations` returns every brief containing either word.
DISCOVERY_PHRASES: tuple[str, ...] = (
    "fabricated citations",
    "nonexistent cases",
    "non-existent cases",
    "citations that do not exist",
    "fictitious cases",
    "no such case exists",
    "could not be located",
    "does not appear to exist",
    "hallucinated citations",
    "artificial intelligence",
)

# Requests are answered from a shared cache when they have been made before, so
# a repeat run of the same phrases costs nothing. Pace anyway: the service
# throttles per minute as well as per day.
REQUEST_INTERVAL_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class Complaint:
    """One document that complains about another document's citations."""

    phrase: str
    docket_id: int
    court_id: str
    docket_number: str
    case_name: str
    date_filed: str | None
    document_id: int
    entry_number: int | None
    description: str
    is_available: bool
    filepath: str | None
    snippet: str


@dataclass
class Discovery:
    """Everything one sweep of the phrases turned up."""

    complaints: list[Complaint] = field(default_factory=list)
    requests_spent: int = 0

    @property
    def dockets(self) -> set[int]:
        """The distinct dockets worth resolving."""
        return {item.docket_id for item in self.complaints}


def _get(base: str, path: str, params: dict[str, str]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{base.rstrip('/')}/{path}?{query}")
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def search_phrase(base: str, phrase: str, *, pages: int = 1) -> tuple[list[Complaint], int]:
    """Search RECAP for one exact phrase and return what complained."""
    found: list[Complaint] = []
    spent = 0
    cursor: str | None = None
    for _ in range(pages):
        params = {"q": f'"{phrase}"', "type": "r", "order_by": "dateFiled desc"}
        if cursor:
            params["cursor"] = cursor
        payload = _get(base, "search/", params)
        spent += 1
        for docket in payload.get("results", []):
            for document in docket.get("recap_documents", []):
                found.append(
                    Complaint(
                        phrase=phrase,
                        docket_id=docket["docket_id"],
                        court_id=docket.get("court_id", ""),
                        docket_number=docket.get("docketNumber", ""),
                        case_name=docket.get("caseName", ""),
                        date_filed=docket.get("dateFiled"),
                        document_id=int(document["id"]),
                        entry_number=document.get("entry_number"),
                        description=(document.get("short_description") or document.get("description") or ""),
                        is_available=bool(document.get("is_available")),
                        filepath=document.get("filepath_local"),
                        snippet=document.get("snippet") or "",
                    )
                )
        cursor = _next_cursor(payload.get("next"))
        if not cursor:
            break
        time.sleep(REQUEST_INTERVAL_SECONDS)
    return found, spent


def _next_cursor(next_url: str | None) -> str | None:
    if not next_url:
        return None
    query = urllib.parse.parse_qs(urllib.parse.urlparse(next_url).query)
    values = query.get("cursor")
    return values[0] if values else None


def discover(
    base: str | None = None,
    *,
    phrases: tuple[str, ...] = DISCOVERY_PHRASES,
    pages: int = 1,
) -> Discovery:
    """Sweep every phrase and collect the documents that complain."""
    endpoint = base or os.environ["COURTLISTENER_BASE_URL"]
    result = Discovery()
    for phrase in phrases:
        try:
            found, spent = search_phrase(endpoint, phrase, pages=pages)
        except Exception as error:
            print(f"  {phrase!r}: {type(error).__name__}: {error}", flush=True)
            continue
        result.complaints.extend(found)
        result.requests_spent += spent
        print(f"  {phrase!r}: {len(found)} documents", flush=True)
        time.sleep(REQUEST_INTERVAL_SECONDS)
    return result
