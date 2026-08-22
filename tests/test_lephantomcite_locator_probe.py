"""Tests for how the locator probe reads a refusal from the citation service."""

from __future__ import annotations

import pytest

from evaluations.lephantomcite import locator_probe


class _Refusal:
    """A CourtListenerError carrying only the field the check reads."""

    def __init__(self, detail: str) -> None:
        self.upstream_detail = detail


@pytest.mark.parametrize(
    ("detail", "spent"),
    [
        # The proxy's own wording, sent once every token it holds is parked.
        ('{"detail": "all CourtListener tokens are exhausted for 2230s"}', True),
        # CourtListener's wording for the per-day allowance.
        ('{"detail": "Request was throttled. Rate limit exceeded: 125/day"}', True),
        # The per-minute burst throttle, which is not exhaustion.
        ('{"detail": "Request was throttled. Rate limit exceeded: 60/minute"}', False),
        ('{"detail": "Not found."}', False),
    ],
)
def test_only_a_spent_allowance_stops_the_sweep(detail: str, *, spent: bool) -> None:
    """Two services refuse in two wordings, and one of them is not exhaustion.

    Knowing only CourtListener's message means a sweep behind the caching proxy
    never detects exhaustion: it keeps asking, is refused, spends its retries
    and writes a `failed` row for every remaining locator. Treating the
    per-minute burst as exhaustion is the opposite error, stopping a sweep that
    would be fine seconds later.
    """
    assert locator_probe._is_quota_refusal(_Refusal(detail)) is spent


def test_the_reported_detail_names_the_refusal() -> None:
    """The message has to say when the allowance returns, not just that it went."""
    detail = locator_probe._quota_detail(
        _Refusal('{"detail": "all CourtListener tokens are exhausted for 2230s"}')
    )

    assert "tokens are exhausted for 2230s" in detail


def test_a_short_form_is_not_looked_up_as_a_first_page() -> None:
    """`550 U.S. at 563` names page 563 of a case that starts at 544.

    Looking that page up as a locator asks whether a case *begins* there, which
    CourtListener answers no -- so a perfectly sound short citation was being
    recorded as unresolved. The production pipeline never does this:
    `validation/citation_lookup/exact.py` skips a non-full citation as
    unsupported. Reporting them separately was worth 343 of the probe's 1,334
    records, 30 of them previously counted as unresolved.
    """
    assert locator_probe.parse_locator("550 U.S. at 563") is None
    assert locator_probe.is_short_form("550 U.S. at 563")


def test_a_full_citation_is_still_a_locator() -> None:
    parts = locator_probe.parse_locator("Bell Atlantic Corp. v. Twombly, 550 U.S. 544 (2007)")

    assert parts is not None
    assert (parts.volume, parts.reporter, parts.page) == ("550", "U.S.", "544")
    assert not locator_probe.is_short_form("Bell Atlantic Corp. v. Twombly, 550 U.S. 544 (2007)")
