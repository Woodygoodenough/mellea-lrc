"""Modal deployment of the CourtListener forward-and-cache proxy.

This module is deployment detail only. The routes, the cache contract and the
token rotation live in `api.py`, `cache.py` and `tokens.py`, where they can be
tested without Modal, R2, or a CourtListener token.

The service is infrastructure, not domain logic: it forwards a request to
CourtListener unchanged, caches the response, and returns it. It does not rename
fields, wrap bodies, or compose several upstream calls into one -- a caller that
asks for `search/` gets CourtListener's own `search/` response, because a proxy
that reshapes responses moves bugs out of the pipeline and into a place nobody
is testing.

What it adds over calling CourtListener directly is what a research sweep needs
and a plain client cannot provide: a shared cache, because the free tier allows
125 requests per token per day and a cached corpus is the only reason an
evaluation is repeatable; and token rotation, because three tokens is three
days' budget rather than one.

Deploy:

    uv run --group modal modal deploy scripts/modal/courtlistener/server.py
"""

import json
import logging
import os
from typing import Any

import modal

logger = logging.getLogger(__name__)

APP_NAME = "courtlistener-access"
DEFAULT_BASE_URL = "https://www.courtlistener.com/api/rest/v4/"
DEFAULT_PREFIX = "courtlistener/v4"
# Held out of the bulk pool on purpose. `TokenPool.from_environment` collects
# only the bare name and numbered suffixes, so this one cannot be drained by a
# sweep; a caller reaches it by asking for it.
RESERVED_TOKEN_NAME = "COURTLISTENER_API_TOKEN_RESERVED"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi[standard]==0.115.*", "httpx==0.28.*", "boto3==1.35.*")
    .add_local_python_source("scripts")
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
    """Wire the app to R2 and the token pool, inside the container that has them."""
    import boto3

    from scripts.modal.courtlistener.api import build_app
    from scripts.modal.courtlistener.cache import object_key, read_envelope
    from scripts.modal.courtlistener.tokens import TokenPool

    bucket = os.environ["R2_BUCKET"]
    prefix = os.environ.get("R2_PREFIX", DEFAULT_PREFIX)
    account = os.environ["R2_ACCOUNT_ID"]
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("R2_REGION", "auto"),
    )
    environ = dict(os.environ)
    pool = TokenPool.from_environment(environ)
    reserved_pool = None
    if environ.get(RESERVED_TOKEN_NAME, "").strip():
        reserved_pool = TokenPool.from_environment(environ, prefix=RESERVED_TOKEN_NAME)
    logger.info(
        "token pools: %d bulk, %d reserved",
        pool.size,
        reserved_pool.size if reserved_pool is not None else 0,
    )

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

    return build_app(
        base_url=os.environ.get("COURTLISTENER_BASE_URL", DEFAULT_BASE_URL),
        pool=pool,
        cache_get=cache_get,
        cache_put=cache_put,
        describe=lambda: {"app": APP_NAME, "bucket": bucket, "prefix": prefix},
        reserved_pool=reserved_pool,
    )
