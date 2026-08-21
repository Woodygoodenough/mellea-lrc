"""Tests for the proxy's request handling, exercised without Modal or R2.

These run the real ASGI app against a stubbed upstream, which is what catches
the failures a unit test of the pieces cannot: the first deployment answered
every request with a 422 because FastAPI could not resolve the handler's
annotations, and every part of it passed its own tests.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from scripts.modal.courtlistener.api import build_app
from scripts.modal.courtlistener.tokens import TokenPool

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
