"""Spend each day's CourtListener allowance filling the response cache.

The evaluation needs roughly 1,200 distinct locator lookups and the free tier
allows 125 requests per token per day, so no single run can finish. This walks
the worklist once a day, skips whatever the cache already holds, and stops the
moment the day's allowance is gone.

**Why this runs inside Modal rather than as a scheduled agent elsewhere.** The
work has to reach the CourtListener proxy, and it needs the API tokens and the
R2 credentials. All three already live here. A cloud agent scheduled outside
cannot reach the proxy at all -- the sandbox's egress policy refuses
`*.modal.run` with a 403 on the CONNECT tunnel, before any request is sent --
and putting the tokens somewhere else to work around that would spread the
credentials for no gain.

The worklist is a static file of volume/reporter/page triples derived once from
the benchmark. Keeping it static means this function needs no dataset download,
no citation parser, and no repository state: it is a list of lookups and a
budget.
"""

import json
import logging
import os
import pathlib
from typing import Any

import modal

from scripts.modal.courtlistener.server import APP_NAME, DEFAULT_BASE_URL, DEFAULT_PREFIX, app, image

logger = logging.getLogger(__name__)

WORKLIST = pathlib.Path(__file__).with_name("warm_locators.json")
# Just after the tokens' daily reset, which sits around 06:20 UTC. Each token's
# window runs 24 hours from its own first request, so starting at a fixed time
# each day keeps the windows anchored there rather than drifting later.
WARM_SCHEDULE = modal.Cron("30 6 * * *")
# Below CourtListener's per-minute burst limit. The daily allowance runs out
# long before pacing matters, but bursting wastes requests on refusals.
REQUEST_INTERVAL_SECONDS = 2.0
# A slow answer says nothing about the citation asked for, so it is retried once
# before being counted against the run.
TRANSPORT_RETRY_SECONDS = 5.0
# Enough consecutive failures to complete means the service is not answering
# rather than answering slowly, and the run should stop instead of spending an
# hour timing out against it.
MAX_CONSECUTIVE_TRANSPORT_ERRORS = 5
FIELDS = ("volume", "reporter", "page")


@app.function(
    image=image.add_local_file(WORKLIST, remote_path="/root/warm_locators.json"),
    secrets=[
        modal.Secret.from_name("courtlistener"),
        modal.Secret.from_name("courtlistener-r2-cache"),
    ],
    schedule=WARM_SCHEDULE,
    timeout=3600,
)
def warm_cache() -> dict[str, Any]:
    """Look up as many uncached locators as the day's allowance allows."""
    import time

    import boto3
    import httpx

    from scripts.modal.courtlistener.cache import (
        build_envelope,
        cache_key,
        object_key,
        read_envelope,
        should_store,
    )
    from scripts.modal.courtlistener.tokens import (
        AllTokensExhausted,
        TokenPool,
        burst_wait_seconds,
        is_burst_refusal,
        is_quota_refusal,
    )

    base_url = os.environ.get("COURTLISTENER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    bucket = os.environ["R2_BUCKET"]
    prefix = os.environ.get("R2_PREFIX", DEFAULT_PREFIX)
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("R2_REGION", "auto"),
    )
    pool = TokenPool.from_environment(dict(os.environ))
    worklist = json.loads(pathlib.Path("/root/warm_locators.json").read_text())

    def cached(key: str) -> bool:
        try:
            raw = s3.get_object(Bucket=bucket, Key=object_key(prefix, key))["Body"].read()
        except s3.exceptions.NoSuchKey:
            return False
        except Exception:
            logger.exception("cache read failed for %s", key)
            return False
        try:
            return read_envelope(json.loads(raw)) is not None
        except ValueError:
            return False

    # Survey the whole worklist before spending anything. Checking cache
    # membership costs no quota, and doing it up front means the run reports
    # what is actually left rather than where it happened to stop -- walking and
    # breaking out reported "2 already cached" on a bucket holding 402 of them.
    from concurrent.futures import ThreadPoolExecutor

    entries = [
        (locator, cache_key("POST", "citation-lookup/", {}, {k: locator[k] for k in FIELDS}))
        for locator in worklist
    ]
    with ThreadPoolExecutor(max_workers=32) as survey:
        present = list(survey.map(lambda item: cached(item[1]), entries))
    pending = [item for item, is_cached in zip(entries, present, strict=True) if not is_cached]
    already = sum(present)
    logger.info("worklist %d: %d cached, %d to fetch", len(entries), already, len(pending))

    fetched = 0
    failed = 0
    consecutive_transport_errors = 0
    ended = "completed"

    with httpx.Client(timeout=45) as client:
        for locator, key in pending:
            data = {k: locator[k] for k in FIELDS}
            try:
                status, payload = _fetch(
                    client, pool, base_url, data, is_quota_refusal, is_burst_refusal, burst_wait_seconds
                )
            except httpx.HTTPError as transport:
                # A timeout or a dropped connection says nothing about this
                # citation, and the run has hundreds of others queued behind
                # it. Count it, keep going, and stop only if the upstream
                # appears to be gone rather than slow.
                failed += 1
                consecutive_transport_errors += 1
                logger.warning(
                    "transport error on %s (%d in a row): %s",
                    data,
                    consecutive_transport_errors,
                    transport,
                )
                if consecutive_transport_errors >= MAX_CONSECUTIVE_TRANSPORT_ERRORS:
                    ended = "upstream_unreachable"
                    logger.error(
                        "%d lookups in a row failed to complete; stopping rather than "
                        "spending the run on a service that is not answering",
                        consecutive_transport_errors,
                    )
                    break
                time.sleep(REQUEST_INTERVAL_SECONDS)
                continue
            except AllTokensExhausted as exhausted:
                ended = "quota_exhausted"
                logger.info(
                    "daily allowance spent after %d fetches; returns in %.0fs",
                    fetched,
                    exhausted.retry_after_seconds,
                )
                break
            consecutive_transport_errors = 0
            if should_store(status, payload):
                s3.put_object(
                    Bucket=bucket,
                    Key=object_key(prefix, key),
                    Body=json.dumps(
                        build_envelope(
                            key,
                            "POST",
                            "citation-lookup/",
                            {},
                            data,
                            f"{base_url}/citation-lookup/",
                            status,
                            payload,
                        )
                    ).encode(),
                    ContentType="application/json",
                )
                fetched += 1
            else:
                failed += 1
            time.sleep(REQUEST_INTERVAL_SECONDS)

    summary = {
        "worklist": len(worklist),
        "already_cached": already,
        "fetched": fetched,
        "not_stored": failed,
        "remaining": len(pending) - fetched - failed,
        "ended": ended,
    }
    logger.info("warm run: %s", json.dumps(summary))
    return summary


def _fetch(
    client: Any,
    pool: Any,
    base_url: str,
    data: dict[str, str],
    is_quota_refusal: Any,
    is_burst_refusal: Any,
    burst_wait_seconds: Any,
) -> tuple[int, Any]:
    """One lookup, moving off a spent token and waiting out a burst refusal.

    A slow answer is retried once rather than allowed to end the lookup. The
    upstream occasionally takes longer than the client will wait, and the run
    that found this had hundreds of locators still queued behind the one that
    timed out.
    """
    import time

    import httpx

    for _ in range(pool.size * 4):
        token = pool.acquire()
        try:
            response = client.post(
                f"{base_url}/citation-lookup/",
                data=data,
                headers={"Authorization": f"Token {token.value}", "Accept": "application/json"},
            )
        except httpx.HTTPError:
            time.sleep(TRANSPORT_RETRY_SECONDS)
            response = client.post(
                f"{base_url}/citation-lookup/",
                data=data,
                headers={"Authorization": f"Token {token.value}", "Accept": "application/json"},
            )
        if is_quota_refusal(response.status_code, response.text):
            pool.park(token, response.text)
            continue
        if is_burst_refusal(response.status_code, response.text):
            time.sleep(burst_wait_seconds(response.text))
            continue
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, None
    pool.acquire()
    msg = "token pool reported availability after refusing every token"
    raise RuntimeError(msg)


@app.local_entrypoint()
def main() -> None:
    """Run one warming pass now, for checking the job before it is scheduled."""
    print(json.dumps(warm_cache.remote(), indent=2))
