"""Narrowing candidates at one locator using the filing's own evidence."""

from __future__ import annotations

import pytest

from mellea_lrc.search import (
    YEAR_TOLERANCE,
    CandidateFacts,
    CitationFacts,
    NarrowingOutcome,
    narrow,
)

LIMIT = 3


def candidate(identifier: str, **fields: str | None) -> CandidateFacts:
    """Build one candidate, defaulting every field it does not name to absent."""
    return CandidateFacts(identifier=identifier, **fields)  # type: ignore[arg-type]


def test_a_candidate_from_another_court_is_excluded() -> None:
    """A court the filing states and the candidate contradicts rules it out."""
    result = narrow(
        CitationFacts(court_id="ca9", year="2007"),
        [
            candidate("right", court_id="ca9", year="2007"),
            candidate("wrong", court_id="ca2", year="2007"),
        ],
        limit=LIMIT,
    )
    assert [item.candidate.identifier for item in result.kept] == ["right"]
    excluded = next(item for item in result.considered if item.candidate.identifier == "wrong")
    assert excluded.outcome is NarrowingOutcome.EXCLUDED_BY_COURT
    assert "ca9" in excluded.reason
    assert "ca2" in excluded.reason


def test_a_year_within_tolerance_is_not_a_disagreement() -> None:
    """One year apart is ordinary and does not exclude; two years apart does."""
    result = narrow(
        CitationFacts(year="2007"),
        [
            candidate("same", year="2007"),
            candidate("next", year=str(2007 + YEAR_TOLERANCE)),
            candidate("far", year=str(2007 + YEAR_TOLERANCE + 1)),
        ],
        limit=LIMIT,
    )
    assert [item.candidate.identifier for item in result.kept] == ["same", "next"]
    far = next(item for item in result.considered if item.candidate.identifier == "far")
    assert far.outcome is NarrowingOutcome.EXCLUDED_BY_YEAR


def test_an_absent_field_excludes_nothing() -> None:
    """A filing that states no court or year rules out no candidate on either."""
    result = narrow(
        CitationFacts(case_name="Doe v. Roe"),
        [
            candidate("a", court_id="ca9", year="1994"),
            candidate("b", court_id="ca2", year="2020"),
        ],
        limit=LIMIT,
    )
    assert len(result.kept) == 2
    assert all(item.court_agrees is None for item in result.considered)
    assert all(item.year_distance is None for item in result.considered)


def test_a_candidate_missing_the_field_is_not_excluded_on_it() -> None:
    """An absence on the candidate's side is not a contradiction either."""
    result = narrow(
        CitationFacts(court_id="ca9", year="2007"),
        [candidate("silent"), candidate("wrong", court_id="ca2")],
        limit=LIMIT,
    )
    assert [item.candidate.identifier for item in result.kept] == ["silent"]


def test_a_name_disagreement_never_excludes() -> None:
    """A disagreeing case name is the defect being looked for, so it is kept."""
    result = narrow(
        CitationFacts(case_name="Cornhill LLC v. Sowers", court_id="nyappdiv", year="2020"),
        [candidate("other", case_name="Goodine v. Evans", court_id="nyappdiv", year="2020")],
        limit=LIMIT,
    )
    assert len(result.kept) == 1
    assert result.kept[0].outcome is NarrowingOutcome.KEPT
    assert result.kept[0].name_agrees is False


def test_an_agreeing_name_ranks_first() -> None:
    """The candidate whose name matches the filing is offered first."""
    result = narrow(
        CitationFacts(case_name="Doe  v.   Roe", court_id="ca9", year="2007"),
        [
            candidate("mismatch", case_name="Smith v. Jones", court_id="ca9", year="2007"),
            candidate("match", case_name="doe v. roe", court_id="ca9", year="2007"),
        ],
        limit=LIMIT,
    )
    assert result.kept[0].candidate.identifier == "match"
    assert result.kept[0].name_agrees is True


def test_excluding_every_candidate_is_withheld() -> None:
    """When the filing contradicts them all, nothing is excluded and it says so."""
    result = narrow(
        CitationFacts(court_id="ca9"),
        [candidate("a", court_id="ca2"), candidate("b", court_id="ca5")],
        limit=LIMIT,
    )
    assert result.exclusions_withheld is True
    assert len(result.kept) == 2
    assert all(item.outcome is NarrowingOutcome.KEPT for item in result.considered)
    assert "none was excluded" in result.summary


def test_narrowing_below_the_limit_offers_the_survivors() -> None:
    """Bringing 5 candidates to 2 under a limit of 3 selects both."""
    citation = CitationFacts(court_id="ca9", year="2007")
    candidates = [
        candidate("keep-1", court_id="ca9", year="2007"),
        candidate("keep-2", court_id="ca9", year="2008"),
        candidate("drop-1", court_id="ca2", year="2007"),
        candidate("drop-2", court_id="ca9", year="1994"),
        candidate("drop-3", court_id="cafc", year="2007"),
    ]
    result = narrow(citation, candidates, limit=LIMIT)
    assert result.separated is True
    assert [item.candidate.identifier for item in result.selected] == ["keep-1", "keep-2"]


def test_narrowing_that_does_not_separate_selects_nothing() -> None:
    """Four survivors under a limit of 3 leaves the decision to a later move."""
    citation = CitationFacts(court_id="ca9", year="2007")
    candidates = [candidate(f"c{index}", court_id="ca9", year="2007") for index in range(4)]
    result = narrow(citation, candidates, limit=LIMIT)
    assert result.separated is False
    assert result.selected == ()
    assert len(result.kept) == 4
    assert "still above the limit" in result.summary


def test_excluded_candidates_are_kept_in_the_record() -> None:
    """Every candidate stays in `considered` so the decision can be reviewed."""
    result = narrow(
        CitationFacts(court_id="ca9"),
        [candidate("a", court_id="ca9"), candidate("b", court_id="ca2")],
        limit=LIMIT,
    )
    assert len(result.considered) == 2
    assert len(result.kept) == 1
    assert result.considered[-1].candidate.identifier == "b"


def test_no_candidates_narrows_to_nothing_without_withholding() -> None:
    """An empty candidate list is not the same as excluding every candidate."""
    result = narrow(CitationFacts(court_id="ca9"), [], limit=LIMIT)
    assert result.kept == ()
    assert result.exclusions_withheld is False
    assert result.separated is True


def test_an_iso_filing_date_is_read_as_a_year() -> None:
    """CourtListener states `dateFiled` as a date, and only its year is compared."""
    result = narrow(
        CitationFacts(year="2007"),
        [candidate("filed", year="2007-11-02")],
        limit=LIMIT,
    )
    assert result.kept[0].year_distance == 0


def test_an_unreadable_year_excludes_nothing() -> None:
    """A year that is not a number is treated as absent rather than as a mismatch."""
    result = narrow(
        CitationFacts(year="2007"),
        [candidate("odd", year="n.d.")],
        limit=LIMIT,
    )
    assert result.kept[0].year_distance is None
    assert result.kept[0].outcome is NarrowingOutcome.KEPT


def test_a_limit_below_one_is_rejected() -> None:
    """A caller willing to evaluate no candidate has nothing to narrow for."""
    with pytest.raises(ValueError, match="at least one candidate"):
        narrow(CitationFacts(), [candidate("a")], limit=0)
