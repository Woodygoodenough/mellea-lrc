"""Bound candidate evaluation without truncating retrieved result sets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mellea_lrc.validation.duplicate_clusters import merge_duplicates
from mellea_lrc.validation.types import (
    CandidateSelectionNode,
    CandidateSelectionOutcome,
    ExactLocatorLookupNode,
    OpinionSearchNode,
    RecapSearchNode,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from mellea_lrc.validation.types import CitationValidation

CANDIDATE_SELECTION_LIMIT = 3


def run_locator_candidate_selection(
    validation: CitationValidation,
    *,
    lookup: ExactLocatorLookupNode,
) -> CandidateSelectionNode:
    """Apply the common guard to an ambiguous exact-locator result set.

    The records are merged first. A lookup returning several records for one
    page is usually one decision the archive holds more than once, so counting
    records treats an unambiguous citation as contested. On the ambiguous
    citations in the last probe this turns 54 of 68 into a single candidate and
    halves the number that exceed the limit, without merging any two records
    that are genuinely different cases.
    """
    distinct = len(merge_duplicates(lookup.candidate_clusters)) if lookup.candidate_clusters else None
    return _selection(
        node_id=f"{validation.citation_id}:locator_candidate_selection",
        retrieval_node_id=lookup.node_id,
        total_candidate_count=lookup.candidate_count,
        distinct_case_count=distinct,
    )


def run_opinion_search_candidate_selection(
    validation: CitationValidation,
    *,
    search: OpinionSearchNode,
) -> CandidateSelectionNode:
    """Apply the common guard to CourtListener opinion-search results."""
    return _selection(
        node_id=f"{validation.citation_id}:opinion_search_candidate_selection",
        retrieval_node_id=search.node_id,
        total_candidate_count=_required_result_count(search.result_count, search.node_id),
    )


def run_recap_search_candidate_selection(
    validation: CitationValidation,
    *,
    search: RecapSearchNode,
) -> CandidateSelectionNode:
    """Apply the common guard to CourtListener RECAP-search results."""
    return _selection(
        node_id=f"{validation.citation_id}:recap_search_candidate_selection",
        retrieval_node_id=search.node_id,
        total_candidate_count=_required_result_count(search.result_count, search.node_id),
    )


def _selection(
    *,
    node_id: str,
    retrieval_node_id: str,
    total_candidate_count: int,
    distinct_case_count: int | None = None,
) -> CandidateSelectionNode:
    """Create the shared selection decision for one retrieved result set.

    The limit is applied to distinct cases where they are known, and to raw
    records otherwise -- a search route reports a count without handing over
    the records, so there is nothing to merge there yet.
    """
    counted = total_candidate_count if distinct_case_count is None else distinct_case_count
    selected_count = total_candidate_count if counted <= CANDIDATE_SELECTION_LIMIT else 0
    outcome = (
        CandidateSelectionOutcome.ALL_SELECTED
        if selected_count == total_candidate_count
        else CandidateSelectionOutcome.DEFERRED_OVER_LIMIT
    )
    merged = (
        "" if distinct_case_count is None else f" ({distinct_case_count} distinct after merging duplicates)"
    )
    outcome_message = (
        f"All {total_candidate_count} returned candidates{merged} are within the current validation scope "
        f"of {CANDIDATE_SELECTION_LIMIT}."
        if outcome is CandidateSelectionOutcome.ALL_SELECTED
        else (
            f"Candidate validation is deferred because {total_candidate_count} returned candidates{merged} "
            f"exceed the current scope of {CANDIDATE_SELECTION_LIMIT}; further refinement is needed before "
            "selecting candidates."
        )
    )
    return CandidateSelectionNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=outcome,
        total_candidate_count=total_candidate_count,
        selected_candidate_count=selected_count,
        selection_limit=CANDIDATE_SELECTION_LIMIT,
        distinct_case_count=distinct_case_count,
        depends_on=(retrieval_node_id,),
        status_message="Candidate selection completed.",
        outcome_message=outcome_message,
    )


def _required_result_count(result_count: int | None, node_id: str) -> int:
    """Require a completed search count before making a selection decision."""
    if result_count is None:
        msg = f"Candidate selection requires a result count from {node_id!r}"
        raise ValueError(msg)
    return result_count
