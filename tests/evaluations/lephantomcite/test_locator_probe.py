"""Tests for the identity probe's outcome vocabulary."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from evaluations.lephantomcite.locator_probe import (
    LocatorParts,
    LookupOutcome,
    _lookup_one,
    names_no_real_reporter,
    parse_locator,
    probe_locators,
    summarize,
)
from mellea_lrc.courtlistener import CourtListenerError


@dataclass
class _Response:
    citation: str
    status: int
    clusters: tuple[object, ...]
    error_message: str | None = None


class _FakeClient:
    """Answers lookups from a table, and counts how many it was asked for."""

    def __init__(self, table: dict[tuple[str, str, str], _Response]) -> None:
        self.table = table
        self.calls: list[tuple[str, str, str]] = []

    def lookup_citation(self, volume: str, reporter: str, page: str) -> _Response:
        self.calls.append((volume, reporter, page))
        try:
            return self.table[(volume, reporter, page)]
        except KeyError:
            return _Response(citation="", status=404, clusters=(), error_message="Citation not found")


@pytest.mark.parametrize(
    ("cited", "expected"),
    [
        ("556 U.S. 662", ("556", "U.S.", "662")),
        ("755 N.E.2d at 598", ("755", "N.E.2d", "598")),
        ("798 F. Supp. 2d 1215", ("798", "F. Supp. 2d", "1215")),
    ],
)
def test_locators_are_parsed_by_the_project_extractor(cited: str, expected: tuple[str, str, str]) -> None:
    """A locator is read here exactly as it would be read in a document."""
    parts = parse_locator(cited)

    assert parts is not None
    assert parts.key == expected


@pytest.mark.parametrize(
    "fabricated",
    [
        "446 Cal. Rptr. 4th 183",
        "982 N.E.4th 701, 702 (1st Cir. 1981)",
        "817 F.5th 625 (11th Cir. 2015)",
    ],
)
def test_a_fabricated_reporter_series_is_refuted_offline(fabricated: str) -> None:
    """No volume or page of a series that does not exist can exist.

    This is a positive finding rather than an absence, and it is reached before
    any request is sent.
    """
    assert parse_locator(fabricated) is None
    assert names_no_real_reporter(fabricated)


@pytest.mark.parametrize(
    "real",
    [
        "801 Fed. Appx. 134",  # a common variation of F. App'x
        "556 U.S. 662",
        "798 F.Supp.2d 1215",
    ],
)
def test_a_real_reporter_is_never_refuted(real: str) -> None:
    """Calling a real series fabricated because a brief abbreviated it differently
    is the worst error this check could make, so variations count as real."""
    assert not (parse_locator(real) is None and names_no_real_reporter(real))


def test_absence_from_the_archive_is_not_refutation() -> None:
    """A real series with no case at that page is unresolved, not a defect."""
    client = _FakeClient({})

    results = probe_locators(["999 U.S. 9999"], client=client, max_workers=1)

    assert results["999 U.S. 9999"].outcome is LookupOutcome.UNRESOLVED


def test_a_single_cluster_resolves_and_several_are_ambiguous() -> None:
    """Identity is settled by one cluster and left open by more than one."""
    client = _FakeClient(
        {
            ("347", "U.S.", "483"): _Response("347 U.S. 483", 200, (object(),)),
            ("1", "F.", "1"): _Response("1 F. 1", 200, (object(), object())),
        }
    )

    results = probe_locators(["347 U.S. 483", "1 F. 1"], client=client, max_workers=1)

    assert results["347 U.S. 483"].outcome is LookupOutcome.RESOLVED
    assert results["1 F. 1"].outcome is LookupOutcome.AMBIGUOUS
    assert results["1 F. 1"].cluster_count == 2


def test_a_repeated_citation_costs_one_lookup() -> None:
    """One authority cited many times in a corpus must not be fetched many times."""
    client = _FakeClient({("347", "U.S.", "483"): _Response("347 U.S. 483", 200, (object(),))})

    probe_locators(["347 U.S. 483", "347 U.S. 483", "347 U.S. 483"], client=client, max_workers=1)

    assert client.calls == [("347", "U.S.", "483")]


def test_a_rate_limit_is_retried_rather_than_recorded_as_a_finding() -> None:
    """A 429 says nothing about the citation, so it must not become an outcome."""
    attempts: list[int] = []

    class _Limited(_FakeClient):
        def lookup_citation(self, volume: str, reporter: str, page: str) -> _Response:
            attempts.append(1)
            if len(attempts) < 2:
                raise CourtListenerError(
                    "rate limited", failure_type="api_limit", upstream_status_code=429, retryable=True
                )
            return _Response("347 U.S. 483", 200, (object(),))

    client = _Limited({})

    results = probe_locators(["347 U.S. 483"], client=client, max_workers=1)

    assert results["347 U.S. 483"].outcome is LookupOutcome.RESOLVED
    assert len(attempts) == 2


def test_a_permanent_failure_is_not_a_finding_either() -> None:
    """A broken lookup is recorded as failed, never as a defect."""

    class _Broken(_FakeClient):
        def lookup_citation(self, volume: str, reporter: str, page: str) -> _Response:
            raise CourtListenerError("bad request", failure_type="upstream_rejected", retryable=False)

    results = probe_locators(["347 U.S. 483"], client=_Broken({}), max_workers=1)

    assert results["347 U.S. 483"].outcome is LookupOutcome.FAILED


def test_a_regulation_is_out_of_scope_rather_than_refuted() -> None:
    """The Federal Register is a real publication that is not a case reporter.

    eyecite types its short form as a short case citation, so it reaches a
    lookup that rejects the reporter. Reading that rejection as fabrication
    would be the exact false positive this vocabulary exists to prevent.
    """
    client = _FakeClient(
        {
            ("80", "Fed. Reg.", "64,545"): _Response(
                citation="",
                status=400,
                clusters=(),
                error_message="Unable to find reporter with abbreviation of 'Fed. Reg.'",
            )
        }
    )

    results = probe_locators(["80 Fed. Reg. at 64,545"], client=client, max_workers=1)

    assert results["80 Fed. Reg. at 64,545"].outcome is LookupOutcome.OUT_OF_SCOPE


def test_an_unknown_case_reporter_is_still_refuted_by_the_lookup() -> None:
    """A rejected reporter that is not a known non-case source is fabrication."""
    client = _FakeClient(
        {
            ("446", "Cal. Rptr. 4th", "183"): _Response(
                citation="",
                status=400,
                clusters=(),
                error_message="Unable to find reporter with abbreviation of 'Cal. Rptr. 4th'",
            )
        }
    )

    # Reached through _lookup_one directly: extraction declines this string, so
    # probe_locators would refute it offline before ever sending a request.
    looked_up = _lookup_one(client, LocatorParts("446", "Cal. Rptr. 4th", "183"))  # noqa: SLF001

    assert looked_up.outcome is LookupOutcome.REFUTED


def test_summarize_reports_every_outcome_including_zeroes() -> None:
    """An outcome that never fired still belongs in a table of outcomes."""
    client = _FakeClient({("347", "U.S.", "483"): _Response("347 U.S. 483", 200, (object(),))})

    results = probe_locators(["347 U.S. 483"], client=client, max_workers=1)
    counts = summarize(list(results.values()))

    assert counts["resolved"] == 1
    assert set(counts) == {outcome.value for outcome in LookupOutcome}
