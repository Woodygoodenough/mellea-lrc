"""Tests for the CourtListener query the fallback search builds."""

import pytest

from mellea_lrc.validation.case_search.mellea_case_name_query_preparation import (
    YEAR_WINDOW,
    _query,
    _QueryTermsProposal,
    _year_span,
)

_TERMS = _QueryTermsProposal(query_plaintiff="Brown", query_defendant="Board of Education")


def test_the_year_the_citation_states_narrows_the_search() -> None:
    """Every citation that reaches this search states a year, and it was unused.

    A filing writing `(10th Cir. 2020)` has stated a date; CourtListener
    indexes dates; and 25 of the 25 citations that passed every gate in the
    last measurement carried one. Leaving it out of the query gave away a
    filter for nothing.
    """
    query = _query(_TERMS, "ca10", "2020")

    assert query == (
        'caseName:("Brown" AND "Board of Education") AND court_id:ca10 '
        "AND dateFiled:[2019-01-01 TO 2021-12-31]"
    )


def test_a_citation_with_no_year_is_searched_exactly_as_before() -> None:
    """The filter is added when a year exists, never invented when one does not."""
    assert _query(_TERMS, "scotus", None) == (
        'caseName:("Brown" AND "Board of Education") AND court_id:scotus'
    )


@pytest.mark.parametrize("year", ["", "n.d.", "20 20", "forthcoming"])
def test_a_year_that_is_not_a_year_narrows_nothing(year: str) -> None:
    assert _year_span(year) is None


def test_the_window_reaches_a_year_either_side() -> None:
    """A December decision is printed in the next year's volume.

    An amended opinion also carries a later date than the one the filing read.
    Searching too wide costs some precision; searching too narrow misses the
    case, which is the failure this project minds more.
    """
    assert YEAR_WINDOW == 1
    assert _year_span("2020") == "dateFiled:[2019-01-01 TO 2021-12-31]"
