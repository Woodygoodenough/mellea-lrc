"""Tests for how the opinion warmer paces itself and reports what it did."""

from __future__ import annotations

from typing import Any

import pytest

from evaluations.lephantomcite import warm_opinions
from mellea_lrc.courtlistener import CourtListenerError


class _Client:
    """A client whose reads are cache hits or misses on a fixed schedule."""

    def __init__(self, cached: dict[str, bool], fails: set[str] | None = None) -> None:
        self._cached = cached
        self._fails = fails or set()
        self.last_response_cached: bool | None = None
        self.read: list[str] = []

    def get_opinion(self, opinion_id: str) -> Any:
        self.read.append(opinion_id)
        if opinion_id in self._fails:
            self.last_response_cached = None
            raise CourtListenerError(
                "CourtListener request timed out",
                failure_type="upstream_timeout",
                retryable=False,
                upstream_detail="timed out",
            )
        self.last_response_cached = self._cached.get(opinion_id, False)
        return object()


@pytest.fixture
def paced(monkeypatch: pytest.MonkeyPatch) -> list[None]:
    """Record every throttle wait without spending the interval."""
    waits: list[None] = []
    monkeypatch.setattr(
        warm_opinions._Throttle,  # noqa: SLF001
        "wait",
        lambda self: waits.append(None),
    )
    return waits


def test_a_cached_read_does_not_cost_a_throttle_interval(paced: list[None]) -> None:
    """The throttle paces requests that reach CourtListener; a cache hit does not.

    A run stops where its allowance ran out, so what it already holds is a
    prefix of the list. Pacing those hits meant every run opened by idling once
    per document it had already fetched -- ten minutes at 310 documents, and
    growing with every night's progress.
    """
    ids = ["a", "b", "c", "d"]
    client = _Client({"a": True, "b": True, "c": True})

    counts = warm_opinions.warm(ids, client)

    assert counts["cached"] == 3
    assert counts["stored"] == 1
    # Only the first read is paced: it cannot know it will hit. Every later
    # read follows a hit, including "d", whose miss is the one mispredict the
    # scheme costs.
    assert len(paced) == 1


def test_a_miss_after_a_hit_restores_pacing(paced: list[None]) -> None:
    """One unpaced request at the boundary is the whole cost of predicting."""
    client = _Client({"a": True, "b": False, "c": False})

    warm_opinions.warm(["a", "b", "c"], client)

    assert len(paced) == 2


def test_an_unreadable_document_is_counted_and_paced(paced: list[None]) -> None:
    """A failure says nothing about the cache, so the next read is paced again."""
    client = _Client({"a": True}, fails={"b"})

    counts = warm_opinions.warm(["a", "b", "c"], client)

    assert counts == {"stored": 1, "cached": 1, "failed": 1, "remaining": 0}
