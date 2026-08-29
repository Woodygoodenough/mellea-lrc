"""Tests for the proxy's request handling, exercised without Modal or R2.

These run the real ASGI app against a stubbed upstream, which is what catches
the failures a unit test of the pieces cannot: the first deployment answered
every request with a 422 because FastAPI could not resolve the handler's
annotations, and every part of it passed its own tests.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from scripts.modal.courtlistener.api import build_app
from scripts.modal.courtlistener.tokens import (
    AllTokensExhausted,
    TokenPool,
    burst_wait_seconds,
)

THROTTLED = "Request was throttled. Rate limit exceeded: 125/day. Expected available in 53034 seconds."
LOOKUP = {"volume": "347", "reporter": "U.S.", "page": "483"}
ANSWER = [{"citation": "347 U.S. 483", "status": 200, "clusters": [{"id": 1}]}]


class _Upstream:
    """Stands in for CourtListener, recording what reached it."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]

    @property
    def tokens_used(self) -> list[str]:
        """The bearer token each request carried, in order."""
        return [r.headers["authorization"].removeprefix("Token ") for r in self.requests]


def _client(
    upstream: _Upstream,
    *,
    cache: dict[str, Any] | None = None,
    tokens: dict[str, str] | None = None,
    reserved: str | None = None,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, dict[str, Any]]:
    store = {} if cache is None else cache
    transport = httpx.MockTransport(upstream.handler)
    real_client = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("scripts.modal.courtlistener.api.httpx.AsyncClient", patched)

    reserved_pool = (
        TokenPool.from_environment({"RESERVED": reserved}, prefix="RESERVED")
        if reserved is not None
        else None
    )
    app = build_app(
        base_url="https://upstream.test/api/rest/v4/",
        pool=TokenPool.from_environment(tokens or {"COURTLISTENER_API_TOKEN_1": "t1"}),
        cache_get=lambda key: store.get(key, {}).get("response"),
        cache_put=lambda key, envelope: store.__setitem__(key, envelope),
        describe=lambda: {"app": "test"},
        reserved_pool=reserved_pool,
    )
    return TestClient(app), store


def test_a_post_is_forwarded_and_answered(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression the first deployment failed: a handler that actually runs.

    FastAPI resolves annotations against the handler's module globals, so a
    route defined inside another function answered every request with a 422
    asking for a query parameter named `request`.
    """
    upstream = _Upstream([httpx.Response(200, json=ANSWER)])
    client, _ = _client(upstream, monkeypatch=monkeypatch)

    response = client.post("/citation-lookup/", data=LOOKUP)

    assert response.status_code == 200
    assert response.json() == ANSWER
    assert response.headers["x-cache"] == "miss"
    assert upstream.requests[0].url.path == "/api/rest/v4/citation-lookup/"


def test_a_get_forwards_its_query_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search is a GET, and its params must reach the upstream unchanged."""
    upstream = _Upstream([httpx.Response(200, json={"count": 0, "results": []})])
    client, _ = _client(upstream, monkeypatch=monkeypatch)

    response = client.get("/search/", params={"q": "Brown", "type": "o"})

    assert response.status_code == 200
    assert dict(upstream.requests[0].url.params) == {"q": "Brown", "type": "o"}


def test_a_second_identical_request_is_served_from_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of the service: one upstream call per distinct request."""
    upstream = _Upstream([httpx.Response(200, json=ANSWER)])
    client, store = _client(upstream, monkeypatch=monkeypatch)

    first = client.post("/citation-lookup/", data=LOOKUP)
    second = client.post("/citation-lookup/", data=LOOKUP)

    assert first.headers["x-cache"] == "miss"
    assert second.headers["x-cache"] == "hit"
    assert second.json() == ANSWER
    assert len(upstream.requests) == 1
    assert len(store) == 1


@pytest.mark.parametrize("status", [400, 401, 404, 500])
def test_a_failed_response_is_never_cached(status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cached failure answers every later request for that citation with it."""
    upstream = _Upstream([httpx.Response(status, json={"detail": "nope"})])
    client, store = _client(upstream, monkeypatch=monkeypatch)

    response = client.post("/citation-lookup/", data=LOOKUP)

    assert response.status_code == status
    assert store == {}


def test_a_spent_token_is_retried_on_the_next_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rotation is what turns one day's allowance into three."""
    upstream = _Upstream([httpx.Response(429, text=THROTTLED), httpx.Response(200, json=ANSWER)])
    client, store = _client(
        upstream,
        tokens={"COURTLISTENER_API_TOKEN_1": "t1", "COURTLISTENER_API_TOKEN_2": "t2"},
        monkeypatch=monkeypatch,
    )

    response = client.post("/citation-lookup/", data=LOOKUP)

    assert response.status_code == 200
    assert upstream.tokens_used == ["t1", "t2"]
    assert len(store) == 1


def test_every_token_spent_answers_with_a_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller that knows the reset can stop rather than retry into a wall."""
    upstream = _Upstream([httpx.Response(429, text=THROTTLED)])
    client, store = _client(
        upstream,
        tokens={"COURTLISTENER_API_TOKEN_1": "t1", "COURTLISTENER_API_TOKEN_2": "t2"},
        monkeypatch=monkeypatch,
    )

    response = client.post("/citation-lookup/", data=LOOKUP)

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert json.loads(response.content)["retry_after_seconds"] > 0
    assert upstream.tokens_used == ["t1", "t2"]
    assert store == {}


def test_health_reports_the_token_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """One number tells you whether rotation is actually live."""
    client, _ = _client(
        _Upstream([httpx.Response(200, json={})]),
        tokens={
            "COURTLISTENER_API_TOKEN_1": "t1",
            "COURTLISTENER_API_TOKEN_2": "t2",
            "COURTLISTENER_API_TOKEN_3": "t3",
        },
        monkeypatch=monkeypatch,
    )

    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["tokens"] == 3


def test_the_reserved_allowance_is_only_used_when_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pool that drains automatically is not reserved at all.

    Its purpose is that a targeted experiment can still run on a day the bulk
    sweeps have spent everything else, so an ordinary request must never reach
    it -- not even when the main pool is exhausted.
    """
    upstream = _Upstream([httpx.Response(429, text=THROTTLED)])
    client, _ = _client(upstream, reserved="reserved-token", monkeypatch=monkeypatch)

    response = client.post("/citation-lookup/", data=LOOKUP)

    assert response.status_code == 429
    assert upstream.tokens_used == ["t1"]
    assert "reserved-token" not in upstream.tokens_used


def test_a_caller_can_ask_for_the_reserved_allowance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Asking by header routes the request to the held-back token."""
    upstream = _Upstream([httpx.Response(200, json=ANSWER)])
    client, store = _client(upstream, reserved="reserved-token", monkeypatch=monkeypatch)

    response = client.post("/citation-lookup/", data=LOOKUP, headers={"x-cl-pool": "reserved"})

    assert response.status_code == 200
    assert response.headers["x-cl-pool"] == "reserved"
    assert upstream.tokens_used == ["reserved-token"]
    assert len(store) == 1


def test_the_reserved_pool_shares_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reserved lookup must not pay twice for what a sweep already stored."""
    upstream = _Upstream([httpx.Response(200, json=ANSWER)])
    client, _ = _client(upstream, reserved="reserved-token", monkeypatch=monkeypatch)

    client.post("/citation-lookup/", data=LOOKUP)
    second = client.post("/citation-lookup/", data=LOOKUP, headers={"x-cl-pool": "reserved"})

    assert second.headers["x-cache"] == "hit"
    assert upstream.tokens_used == ["t1"]


def test_health_reports_both_pools(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two numbers say whether rotation and the reserve are both live."""
    client, _ = _client(
        _Upstream([httpx.Response(200, json={})]),
        tokens={"COURTLISTENER_API_TOKEN_1": "t1", "COURTLISTENER_API_TOKEN_2": "t2"},
        reserved="reserved-token",
        monkeypatch=monkeypatch,
    )

    body = client.get("/health").json()

    assert body["tokens"] == 2
    assert body["reserved_tokens"] == 1


def test_asking_for_a_reserved_pool_that_is_not_configured_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Silently using the main allowance would spend the wrong budget and pass.

    A run that asked for the reserve and got the bulk pool instead would look
    successful while draining exactly what it was trying not to touch.
    """
    upstream = _Upstream([httpx.Response(200, json=ANSWER)])
    client, _ = _client(upstream, monkeypatch=monkeypatch)

    response = client.post("/citation-lookup/", data=LOOKUP, headers={"x-cl-pool": "reserved"})

    assert response.status_code == 503
    assert upstream.requests == []


BURST = "Request was throttled. Rate limit exceeded: 60/minute. Expected available in 12 seconds."


def test_a_burst_refusal_moves_to_the_next_token_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A per-minute throttle is counted per token, so the others are fine.

    The pool rotates on every acquire, so stepping the throttled token aside
    reaches the next one at once. Sleeping first idles every token for one
    token's limit -- a night of warming spent 75 minutes doing exactly that.
    """
    upstream = _Upstream([httpx.Response(429, text=BURST), httpx.Response(200, json=ANSWER)])
    client, store = _client(
        upstream,
        tokens={"COURTLISTENER_API_TOKEN_1": "t1", "COURTLISTENER_API_TOKEN_2": "t2"},
        monkeypatch=monkeypatch,
    )

    began = time.perf_counter()
    response = client.post("/citation-lookup/", data=LOOKUP)
    elapsed = time.perf_counter() - began

    assert response.status_code == 200
    assert upstream.tokens_used == ["t1", "t2"]
    assert len(store) == 1
    # The throttle named twelve seconds. Nothing may wait them out in-request.
    assert elapsed < 1.0


def test_every_token_throttled_refuses_with_the_soonest_one_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Holding the connection is what turned a throttle into an upstream timeout.

    Each sleep was capped but their sum was not, so one request could outlast
    any caller's timeout and be recorded as a network failure against a service
    answering in under a second. Now every token steps aside for the seconds it
    names and the caller is told the shortest of those, so it comes back when
    the first token does rather than after the longest window any one named.
    """
    upstream = _Upstream([httpx.Response(429, text=BURST)])
    client, store = _client(
        upstream,
        tokens={"COURTLISTENER_API_TOKEN_1": "t1", "COURTLISTENER_API_TOKEN_2": "t2"},
        monkeypatch=monkeypatch,
    )

    began = time.perf_counter()
    response = client.post("/citation-lookup/", data=LOOKUP)
    elapsed = time.perf_counter() - began

    assert response.status_code == 429
    assert upstream.tokens_used == ["t1", "t2"]
    retry_after = json.loads(response.content)["retry_after_seconds"]
    assert 0 < retry_after <= 12
    assert store == {}
    assert elapsed < 1.0


def test_a_burst_refusal_does_not_park_a_token_for_the_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parking for a minute-long throttle would empty the pool in one burst."""
    pool = TokenPool.from_environment({"COURTLISTENER_API_TOKEN_1": "t1"})
    pool.park_briefly(pool.tokens[0], burst_wait_seconds(BURST))

    with pytest.raises(AllTokensExhausted) as refusal:
        pool.acquire()

    assert refusal.value.retry_after_seconds <= 12


def test_health_reports_what_each_token_has_left(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pool that says "available" and then refuses is what this exists to explain."""
    client, _ = _client(
        _Upstream([httpx.Response(200, json={"ok": True})]),
        tokens={"COURTLISTENER_API_TOKEN_1": "t1", "COURTLISTENER_API_TOKEN_2": "t2"},
        monkeypatch=monkeypatch,
    )
    client.get("/dockets/1/")

    body = client.get("/health").json()

    assert [entry["token"] for entry in body["pool"]] == [
        "COURTLISTENER_API_TOKEN_1",
        "COURTLISTENER_API_TOKEN_2",
    ]
    assert sum(entry["served"] for entry in body["pool"]) == 1
    assert all(entry["available_in"] == 0 for entry in body["pool"])


def test_health_reports_the_wait_on_a_spent_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """The upstream's own wording is the trustworthy part, so it is carried through."""
    refusal = "Request was throttled. Rate limit exceeded: 125/day. Expected available in 3600 seconds."
    client, _ = _client(
        _Upstream([httpx.Response(429, text=refusal), httpx.Response(200, json={"ok": True})]),
        tokens={"COURTLISTENER_API_TOKEN_1": "t1", "COURTLISTENER_API_TOKEN_2": "t2"},
        monkeypatch=monkeypatch,
    )
    client.get("/dockets/1/")

    spent = [entry for entry in client.get("/health").json()["pool"] if entry["available_in"]]

    assert len(spent) == 1
    assert spent[0]["available_in"] == 3600
    assert "125/day" in spent[0]["last_refusal"]


def test_health_reports_no_token_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """/health is reachable by anything that can reach the proxy."""
    client, _ = _client(
        _Upstream([httpx.Response(200, json={})]),
        tokens={"COURTLISTENER_API_TOKEN_1": "a-real-secret"},
        monkeypatch=monkeypatch,
    )

    assert "a-real-secret" not in client.get("/health").text
