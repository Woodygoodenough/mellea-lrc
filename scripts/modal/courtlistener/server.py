"""Modal deployment of the CourtListener forward-and-cache proxy.

The service is infrastructure, not domain logic: it forwards a request to
CourtListener unchanged, caches the response, and returns it. It does not
rename fields, wrap bodies, or compose several upstream calls into one -- a
caller that asks for `search/` gets CourtListener's own `search/` response,
because a proxy that reshapes responses moves bugs out of the pipeline and into
a place nobody is testing.

What it adds over calling CourtListener directly is the two things a research
sweep needs and a plain client cannot provide:

- **A shared cache.** The free tier allows 125 requests per token per day, so a
  cached corpus is the only reason an evaluation is repeatable at all.
- **Token rotation.** Three tokens is three days' budget rather than one.

Deploy:

    uv run --group modal modal deploy scripts/modal/courtlistener/server.py
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import modal

logger = logging.getLogger(__name__)

APP_NAME = "courtlistener-access"
UPSTREAM_TIMEOUT_SECONDS = 45

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi[standard]==0.115.*", "httpx==0.28.*", "boto3==1.35.*")
    .add_local_python_source("cache", "tokens")
)

app = modal.App(APP_NAME)


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("courtlistener"),
        modal.Secret.from_name("courtlistener-r2-cache"),
    ],
    min_containers=0,
    timeout=300,
)
@modal.asgi_app()
def web() -> Any:
    """Build the ASGI app inside the container, where the secrets are present."""
    import boto3
    import httpx
    from cache import build_envelope, cache_key, object_key, read_envelope, should_store
    from fastapi import FastAPI, Request, Response
    from tokens import AllTokensExhausted, TokenPool, is_quota_refusal

    base_url = os.environ.get("COURTLISTENER_BASE_URL", "https://www.courtlistener.com/api/rest/v4/")
    bucket = os.environ["R2_BUCKET"]
    prefix = os.environ.get("R2_PREFIX", "courtlistener/v4")
    account = os.environ["R2_ACCOUNT_ID"]

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("R2_REGION", "auto"),
    )
    pool = TokenPool.from_environment(dict(os.environ))
    logger.info("token pool holds %d tokens", pool.size)

    api = FastAPI(title="CourtListener access", version="2")

    def cache_get(key: str) -> Any | None:
        try:
            raw = s3.get_object(Bucket=bucket, Key=object_key(prefix, key))["Body"].read()
        except s3.exceptions.NoSuchKey:
            return None
        except Exception:
            logger.exception("cache read failed for %s", key)
            return None
        try:
            stored = json.loads(raw)
        except ValueError:
            logger.warning("cached object %s is not JSON", key)
            return None
        cached = read_envelope(stored)
        return None if cached is None else cached.payload

    def cache_put(key: str, envelope: dict[str, Any]) -> None:
        try:
            s3.put_object(
                Bucket=bucket,
                Key=object_key(prefix, key),
                Body=json.dumps(envelope).encode(),
                ContentType="application/json",
            )
        except Exception:
            # A cache that cannot be written must not fail a request that
            # already has its answer.
            logger.exception("cache write failed for %s", key)

    @api.get("/health")
    def health() -> dict[str, Any]:
        """Report that the service is up and how many tokens it holds."""
        return {"status": "ok", "app": APP_NAME, "tokens": pool.size, "bucket": bucket}

    @api.api_route("/{endpoint:path}", methods=["GET", "POST"])
    async def forward(endpoint: str, request: Request) -> Response:
        """Forward one request to CourtListener, serving it from cache when stored."""
        params = dict(request.query_params)
        data: dict[str, str] = {}
        if request.method == "POST":
            form = await request.form()
            data = {key: str(value) for key, value in form.items()}

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
            token = pool.acquire()
        except AllTokensExhausted as exhausted:
            return Response(
                content=json.dumps(
                    {
                        "detail": str(exhausted),
                        "retry_after_seconds": round(exhausted.retry_after_seconds),
                    }
                ),
                status_code=429,
                media_type="application/json",
                headers={"x-cache": "miss", "retry-after": str(round(exhausted.retry_after_seconds))},
            )

        headers = {"Authorization": f"Token {token.value}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
            upstream = await client.request(
                request.method, url, params=params or None, data=data or None, headers=headers
            )

        if is_quota_refusal(upstream.status_code, upstream.text):
            pool.park(token, upstream.text)
            # Retry once on the next token rather than returning a refusal that
            # only reflects this one being spent.
            try:
                token = pool.acquire()
            except AllTokensExhausted:
                return Response(
                    content=upstream.content,
                    status_code=upstream.status_code,
                    media_type="application/json",
                    headers={"x-cache": "miss"},
                )
            headers["Authorization"] = f"Token {token.value}"
            async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
                upstream = await client.request(
                    request.method, url, params=params or None, data=data or None, headers=headers
                )
            if is_quota_refusal(upstream.status_code, upstream.text):
                pool.park(token, upstream.text)

        try:
            payload = upstream.json()
        except ValueError:
            payload = None

        if should_store(upstream.status_code, payload):
            cache_put(
                key,
                build_envelope(
                    key, request.method, endpoint, params, data, url, upstream.status_code, payload
                ),
            )

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
            headers={"x-cache": "miss"},
        )

    return api
