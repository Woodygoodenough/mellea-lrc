"""Tests for the CourtListener proxy's cache contract."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from scripts.modal.courtlistener.cache import (
    build_envelope,
    cache_key,
    object_key,
    read_envelope,
    should_store,
)

FIXTURES = json.loads((Path(__file__).parent / "cache_key_fixtures.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f"{f['method']}:{f['endpoint'][:28]}")
def test_cache_key_matches_what_is_already_stored(fixture: dict[str, object]) -> None:
    """The key is pinned to real objects in the bucket, and must never move.

    CourtListener allows 125 requests per token per day. A key change orphans
    every response already cached and costs weeks of quota to rebuild, so this
    test exists to make that change impossible to land by accident.
    """
    derived = cache_key(
        str(fixture["method"]),
        str(fixture["endpoint"]),
        fixture["params"],  # type: ignore[arg-type]
        fixture["data"],  # type: ignore[arg-type]
    )

    assert derived == fixture["key"]


def test_argument_order_does_not_produce_a_second_key() -> None:
    """One request must have one key however its fields were assembled."""
    first = cache_key("POST", "citation-lookup/", {}, {"volume": "347", "reporter": "U.S.", "page": "483"})
    second = cache_key("POST", "citation-lookup/", {}, {"page": "483", "volume": "347", "reporter": "U.S."})

    assert first == second


def test_method_case_does_not_produce_a_second_key() -> None:
    """A lowercase verb addresses the same upstream request."""
    assert cache_key("get", "search/", {"q": "x"}) == cache_key("GET", "search/", {"q": "x"})


def test_object_key_places_the_key_under_the_prefix() -> None:
    """Objects live at `{prefix}/{key}.json`, with the prefix given either way."""
    assert object_key("courtlistener/v4", "abc") == "courtlistener/v4/abc.json"
    assert object_key("/courtlistener/v4/", "abc") == "courtlistener/v4/abc.json"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 502])
def test_a_failure_is_never_stored(status: int) -> None:
    """A cached error answers every later request for that citation with it.

    A cached 429 freezes a rate limit into the record and a cached 401 freezes a
    credential problem into it, neither of which has anything to do with the
    citation. Five such objects were found in the live bucket and removed.
    """
    assert should_store(status, {"detail": "nope"}) is False


@pytest.mark.parametrize("status", [200, 201, 204])
def test_a_success_with_a_body_is_stored(status: int) -> None:
    """The ordinary case: an answer worth not asking for twice."""
    assert should_store(status, [{"citation": "347 U.S. 483"}]) is True


def test_a_success_without_a_body_is_not_stored() -> None:
    """An unparseable success is not an answer, so it is not cached as one."""
    assert should_store(200, None) is False


def test_the_current_envelope_round_trips() -> None:
    """What the proxy writes, the proxy reads."""
    payload = [{"citation": "347 U.S. 483", "clusters": [{"id": 1}]}]
    envelope = build_envelope(
        key="k",
        method="post",
        endpoint="citation-lookup/",
        params={},
        data={"volume": "347"},
        url="https://example.test/citation-lookup/",
        status_code=200,
        payload=payload,
    )

    cached = read_envelope(envelope)

    assert cached is not None
    assert cached.payload == payload
    assert cached.status_code == 200
    assert cached.envelope_version == 2
    assert envelope["method"] == "POST"


def test_the_older_envelope_is_still_readable() -> None:
    """Several hundred objects predate the current envelope and all hold answers.

    They store the body base64-encoded under `content` and carry no request
    metadata. Treating them as unreadable would discard them and spend days of
    quota re-fetching what is already in the bucket.
    """
    payload = [{"citation": "190 B.R. 471", "clusters": []}]
    stored = {
        "status_code": 200,
        "content": base64.b64encode(json.dumps(payload).encode()).decode(),
        "content_type": "application/json",
    }

    cached = read_envelope(stored)

    assert cached is not None
    assert cached.payload == payload
    assert cached.envelope_version == 1


@pytest.mark.parametrize(
    "stored",
    [
        {"status_code": 429, "response": None},
        {"status_code": 200, "content": "not-base64!!"},
        {"status_code": 200},
        {"response": [{"a": 1}]},
    ],
    ids=["failure-with-no-body", "undecodable-content", "no-body-at-all", "no-status"],
)
def test_an_unusable_stored_object_reads_as_a_miss(stored: dict[str, object]) -> None:
    """A record carrying no answer must not be served as one."""
    assert read_envelope(stored) is None
