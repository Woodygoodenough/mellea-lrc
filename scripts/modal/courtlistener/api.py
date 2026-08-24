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

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response

from scripts.modal.courtlistener.cache import build_envelope, cache_key, should_store
from scripts.modal.courtlistener.tokens import (
    AllTokensExhausted,
    TokenPool,
    burst_wait_seconds,
    is_burst_refusal,
    is_quota_refusal,
)

logger = logging.getLogger(__name__)

UPSTREAM_TIMEOUT_SECONDS = 45
HTTP_TOO_MANY_REQUESTS = 429
# How many times a burst refusal may be waited out before giving up on a request.
BURST_RETRIES = 3
# How long one request may spend waiting out burst refusals, across every retry.
#
# `MAX_BURST_WAIT_SECONDS` bounds a single sleep but nothing bounded their sum,
# so a request could sit here for that cap times the retry count -- far past any
# caller's timeout. The caller then reports an upstream timeout for a service
# that was answering in under a second, which is exactly the wrong diagnosis and
# hides a throttle behind a network-looking failure. Past this budget the caller
# is told to come back, with the wait attached, instead of being held.
MAX_TOTAL_BURST_WAIT_SECONDS = 30.0
# A caller asked for an allowance this deployment does not have.
HTTP_MISCONFIGURED = 503

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
        if wants_reserved and reserved_pool is None:
            # Falling back to the main pool would spend the wrong allowance and
            # report success, so a caller asking for an allowance that does not
            # exist has to hear about it.
            return Response(
                content=json.dumps({"detail": f"no {RESERVED_POOL} pool is configured"}),
                status_code=HTTP_MISCONFIGURED,
                media_type="application/json",
                headers={"x-cache": "miss"},
            )
        chosen = reserved_pool if wants_reserved else pool

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

    A burst limit is the opposite and is waited out in place, but only within
    `MAX_TOTAL_BURST_WAIT_SECONDS`. Beyond it the caller is refused with the
    remaining wait attached: a short wait is what tells the caller apart a
    throttle from a spent day, so refusing quickly keeps that signal intact
    where holding the connection destroys it.
    """
    waited = 0.0
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
        for _ in range(pool.size * (BURST_RETRIES + 1)):
            token = pool.acquire()
            response = await client.request(
                method,
                url,
                params=params or None,
                data=data or None,
                headers={"Authorization": f"Token {token.value}", "Accept": "application/json"},
            )
            if is_quota_refusal(response.status_code, response.text):
                pool.park(token, response.text)
                continue
            if is_burst_refusal(response.status_code, response.text):
                # A short-window throttle clears in seconds. Waiting it out
                # keeps the token; parking it would empty the pool over
                # something that is not an exhausted allowance at all.
                wait = burst_wait_seconds(response.text)
                if waited + wait > MAX_TOTAL_BURST_WAIT_SECONDS:
                    logger.info("burst wait budget spent after %.0fs; refusing", waited)
                    raise AllTokensExhausted(wait)
                await asyncio.sleep(wait)
                waited += wait
                continue
            return (
                response.status_code,
                response.content,
                response.headers.get("content-type", "application/json"),
            )
    # Every token refused within this request. Asking the pool once more raises
    # AllTokensExhausted carrying the earliest reset, which is what the caller
    # needs in order to stop rather than retry.
    pool.acquire()
    # The pool still has a usable token, so every refusal here was a burst
    # limit. That is a 429 with a short wait, not a 500: the request is fine and
    # will succeed shortly.
    raise AllTokensExhausted(MAX_TOTAL_BURST_WAIT_SECONDS)
