"""Find and remove cache objects that carry no answer.

    python -m scripts.modal.courtlistener.repair_cache            # report only
    python -m scripts.modal.courtlistener.repair_cache --delete   # remove them

A cache object is unusable when it holds no response the proxy could serve: a
refusal stored as though it were an answer, an empty body, or content that no
longer decodes. Serving one answers every later request for that citation with
it, and the reasons behind it -- a rate limit, an expired credential -- have
nothing to do with the citation.

The decision is `read_envelope`, the same function the proxy reads with, so this
tool cannot disagree with the service about what is servable.

**It is not enough for an object to look unfamiliar.** Several hundred objects
in the live bucket predate the current envelope and store their body
base64-encoded under `content`; every one of them holds a real response. Deleting
them because they lack the newer metadata would discard days of quota. Nothing
is removed without `--delete`, and what is removed is written to a backup file
first.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from scripts.modal.courtlistener.cache import read_envelope

logger = logging.getLogger(__name__)

DEFAULT_PREFIX = "courtlistener/v4"
SCAN_WORKERS = 32


def _client() -> Any:
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def scan(s3: Any, bucket: str, prefix: str) -> tuple[list[str], list[tuple[str, dict[str, Any]]]]:
    """Return every object key, and the ones holding no servable response."""
    paginator = s3.get_paginator("list_objects_v2")
    keys = [
        item["Key"]
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix.strip("/") + "/")
        for item in page.get("Contents", [])
    ]

    def probe(key: str) -> tuple[str, dict[str, Any]] | None:
        try:
            stored = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
        except ValueError:
            return (key, {"error": "not JSON"})
        except Exception:
            logger.exception("could not read %s", key)
            return None
        if not isinstance(stored, dict) or read_envelope(stored) is None:
            summary = {
                field: stored.get(field)
                for field in ("status_code", "endpoint", "method")
                if isinstance(stored, dict)
            }
            return (key, {"summary": summary, "stored": stored})
        return None

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
        unusable = [row for row in pool.map(probe, keys) if row is not None]
    return keys, unusable


def main() -> None:
    """Report unusable cache objects, and remove them only when asked."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=os.environ.get("R2_BUCKET", "cl-cache"))
    parser.add_argument("--prefix", default=os.environ.get("R2_PREFIX", DEFAULT_PREFIX))
    parser.add_argument("--delete", action="store_true", help="remove what the scan finds")
    parser.add_argument(
        "--backup",
        type=Path,
        default=Path("cache-removed.json"),
        help="where the removed objects are written before deletion",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    s3 = _client()
    keys, unusable = scan(s3, args.bucket, args.prefix)
    logger.info("scanned %d objects in %s/%s", len(keys), args.bucket, args.prefix)
    logger.info("unusable: %d", len(unusable))
    for key, detail in unusable[:20]:
        logger.info("  %s  %s", key.rsplit("/", 1)[-1][:24], detail.get("summary") or detail.get("error"))

    if not unusable:
        logger.info("nothing to remove")
        return
    if not args.delete:
        logger.info("report only; pass --delete to remove them")
        return

    args.backup.write_text(
        json.dumps({key: detail.get("stored") for key, detail in unusable}, indent=2), encoding="utf-8"
    )
    logger.info("backed up %d objects to %s", len(unusable), args.backup)
    for key, _ in unusable:
        s3.delete_object(Bucket=args.bucket, Key=key)
    logger.info("removed %d objects", len(unusable))


if __name__ == "__main__":
    main()
