"""Read-through R2 cache for CourtListener responses.

Two things about this cache are load-bearing and easy to get wrong.

**The key must not change.** Thousands of responses are already stored under a
scheme this module reproduces exactly, and CourtListener's free tier allows 125
requests per token per day, so re-fetching a cache that a key change orphaned
costs weeks. `cache_key` is pinned by a test against recorded fixtures.

**Only a success may be stored.** A cached error answers every later request for
that citation with the same error and never retries -- a cached 429 freezes a
rate limit into the record, and a cached 401 freezes a credential problem into
it. `should_store` is the single place that decides, and it says yes only to a
2xx with a body.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

CACHE_ENVELOPE_VERSION = 2
_HTTP_OK = 200
_HTTP_MULTIPLE_CHOICES = 300


@dataclass(frozen=True, slots=True)
class CachedResponse:
    """One stored upstream response, in whichever envelope it was written."""

    status_code: int
    payload: Any
    envelope_version: int


def cache_key(
    method: str,
    endpoint: str,
    params: Mapping[str, str] | None = None,
    data: Mapping[str, str] | None = None,
) -> str:
    """Derive the stable cache key for one upstream request.

    `endpoint` is the path below the API root with no leading slash and its
    trailing slash kept, exactly as CourtListener addresses it -- `search/`,
    `citation-lookup/`, `dockets/42/`. Params and data are url-encoded with
    their keys sorted, so argument order never produces a second key for one
    request.

    Do not change this function. Every object already in the bucket is stored
    under what it returns.
    """
    parts = [
        method.upper(),
        endpoint,
        urlencode(sorted((params or {}).items())),
        urlencode(sorted((data or {}).items())),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def object_key(prefix: str, key: str) -> str:
    """Place one cache key inside the bucket's prefix."""
    return f"{prefix.strip('/')}/{key}.json"


def should_store(status_code: int, payload: Any) -> bool:
    """Whether an upstream response may be cached.

    A failure is never stored. It would be returned in place of every later
    request for the same citation, and the reasons it failed -- a rate limit, an
    expired credential, an upstream outage -- have nothing to do with the
    citation and will not be true for long.
    """
    if not _HTTP_OK <= status_code < _HTTP_MULTIPLE_CHOICES:
        return False
    return payload is not None


def build_envelope(
    key: str,
    method: str,
    endpoint: str,
    params: Mapping[str, str] | None,
    data: Mapping[str, str] | None,
    url: str,
    status_code: int,
    payload: Any,
) -> dict[str, Any]:
    """Build the stored record, keeping the fields the current envelope carries."""
    return {
        "key": key,
        "method": method.upper(),
        "endpoint": endpoint,
        "params": dict(params or {}),
        "data": dict(data or {}),
        "url": url,
        "status_code": status_code,
        "response": payload,
        "cached_at": datetime.now(UTC).isoformat(),
        "envelope_version": CACHE_ENVELOPE_VERSION,
    }


def read_envelope(raw: Mapping[str, Any]) -> CachedResponse | None:
    """Read a stored record written by either envelope this bucket contains.

    The older envelope stores the upstream body base64-encoded under `content`
    and carries no request metadata. Several hundred objects are in that shape
    and every one of them holds a real response, so treating it as unreadable
    would discard them and spend days of quota re-fetching what is already here.
    """
    status = raw.get("status_code")
    if not isinstance(status, int):
        return None

    if "response" in raw:
        payload = raw.get("response")
        if payload is None:
            return None
        return CachedResponse(status_code=status, payload=payload, envelope_version=2)

    content = raw.get("content")
    if not isinstance(content, str) or not content:
        return None
    try:
        payload = json.loads(base64.b64decode(content))
    except (ValueError, TypeError):
        logger.warning("cached object has undecodable content")
        return None
    return CachedResponse(status_code=status, payload=payload, envelope_version=1)
