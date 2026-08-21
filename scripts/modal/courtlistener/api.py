"""The forward-and-cache ASGI app, built at module scope.

The routes live here rather than inside the Modal function because FastAPI
resolves a handler's annotations against the handler's **module globals**. A
route defined inside another function cannot see names imported into that
function's locals, so `request: Request` resolves to nothing and every request
fails with a 422 asking for a query parameter called `request`. Defining the
routes at module scope, where `Request` is a module global, is what makes the
annotations resolvable.

`build_app` takes its dependencies as arguments so the same module can be
exercised without Modal, R2, or a CourtListener token.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response

from scripts.modal.courtlistener.cache import build_envelope, cache_key, should_store
from scripts.modal.courtlistener.tokens import AllTokensExhausted, TokenPool, is_quota_refusal

logger = logging.getLogger(__name__)

UPSTREAM_TIMEOUT_SECONDS = 45
HTTP_TOO_MANY_REQUESTS = 429

# A caller opts in to the reserved allowance with this header. It is deliberately
# opt-in rather than a fallback: the reserved token exists so that a small,
# targeted experiment can still run after a bulk sweep has spent the rest, and a
# pool that is drained automatically would not be reserved at all.
POOL_HEADER = "x-cl-pool"
RESERVED_POOL = "reserved"


def build_app(
    *,
    base_url: str,
    pool: TokenPool,
    cache_get: Callable[[str], Any | None],
    cache_put: Callable[[str, dict[str, Any]], None],
    describe: Callable[[], dict[str, Any]],
    reserved_pool: TokenPool | None = None,
) -> FastAPI:
    """Assemble the proxy around its cache and token pools.

    `reserved_pool` holds an allowance the bulk sweeps never touch, reachable
    only by a caller that asks for it by header. Its purpose is that a targeted
    experiment can still run on a day the sweeps have spent everything else.
    """
    api = FastAPI(title="CourtListener access", version="2")

    @api.get("/health")
    def health() -> dict[str, Any]:
        """Report that the service is up, and what it is configured with."""
        return {
            "status": "ok",
            "tokens": pool.size,
            "reserved_tokens": reserved_pool.size if reserved_pool is not None else 0,
            **describe(),
        }

    @api.api_route("/{endpoint:path}", methods=["GET", "POST"])
    async def forward(endpoint: str, request: Request) -> Response:
        """Forward one request to CourtListener, serving it from cache when stored."""
        params = dict(request.query_params)
        data: dict[str, str] = {}
        if request.method == "POST":
            form = await request.form()
            data = {key: str(value) for key, value in form.items()}

        wants_reserved = request.headers.get(POOL_HEADER, "").strip().lower() == RESERVED_POOL
        chosen = reserved_pool if (wants_reserved and reserved_pool is not None) else pool

        key = cache_key(request.method, endpoint, params, data)
        cached = cache_get(key)
        if cached is not None:
            return Response(
                content=json.dumps(cached),
                media_type="application/json",
                headers={"x-cache": "hit"},
            )

        url = base_url.rstrip("/") + "/" + endpoint
        try:
            status, payload_bytes, content_type = await _send(chosen, request.method, url, params, data)
        except AllTokensExhausted as exhausted:
            retry_after = round(exhausted.retry_after_seconds)
            return Response(
                content=json.dumps({"detail": str(exhausted), "retry_after_seconds": retry_after}),
                status_code=HTTP_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={
                    "x-cache": "miss",
                    "x-cl-pool": RESERVED_POOL if chosen is reserved_pool else "main",
                    "retry-after": str(retry_after),
                },
            )

        try:
            payload = json.loads(payload_bytes)
        except ValueError:
            payload = None

        if should_store(status, payload):
            cache_put(
                key,
                build_envelope(key, request.method, endpoint, params, data, url, status, payload),
            )

        return Response(
            content=payload_bytes,
            status_code=status,
            media_type=content_type,
            headers={
                "x-cache": "miss",
                "x-cl-pool": RESERVED_POOL if chosen is reserved_pool else "main",
            },
        )

    return api


async def _send(
    pool: TokenPool,
    method: str,
    url: str,
    params: dict[str, str],
    data: dict[str, str],
) -> tuple[int, bytes, str]:
    """Send the request, moving to the next token when one's allowance is spent.

    A daily cap is not a rate to wait out, so a refused token is parked and the
    request is retried on the next one. When every token is parked the caller
    gets `AllTokensExhausted` and can stop rather than retry into a wall.
    """
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
        for _ in range(pool.size):
            token = pool.acquire()
            response = await client.request(
                method,
                url,
                params=params or None,
                data=data or None,
                headers={"Authorization": f"Token {token.value}", "Accept": "application/json"},
            )
            if not is_quota_refusal(response.status_code, response.text):
                return (
                    response.status_code,
                    response.content,
                    response.headers.get("content-type", "application/json"),
                )
            pool.park(token, response.text)
    # Every token refused within this request. Asking the pool once more raises
    # AllTokensExhausted carrying the earliest reset, which is what the caller
    # needs in order to stop rather than retry.
    pool.acquire()
    msg = "token pool reported availability after refusing every token"
    raise RuntimeError(msg)
