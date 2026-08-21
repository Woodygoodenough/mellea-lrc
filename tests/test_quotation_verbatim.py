"""Tests for checking a filed quotation against the page it cites."""

from __future__ import annotations

import pytest

from mellea_lrc.core.spans import Span
from mellea_lrc.validation.quotation import (
    QuotationOutcome,
    check_quotation,
    check_quotations,
    find_quotations,
)

PAGE = (
    "To survive a motion to dismiss, a complaint must contain sufficient factual matter, "
    "accepted as true, to state a claim to relief that is plausible on its face. Where a "
    "complaint pleads facts that are merely consistent with a defendant's liability, it "
    "stops short of the line between possibility and plausibility of entitlement to relief."
)


def _only(citing: str) -> object:
    (finding,) = check_quotations(PAGE, citing)
    return finding


def test_a_faithful_quotation_is_verbatim() -> None:
    """The plain case: the characters are on the page."""
    finding = _only(
        'The Court held that a complaint must "contain sufficient factual matter, accepted '
        'as true, to state a claim to relief that is plausible on its face."'
    )

    assert finding.outcome is QuotationOutcome.VERBATIM
    assert finding.page_span is not None
    assert PAGE[finding.page_span.start : finding.page_span.end].startswith("contain sufficient")


def test_bluebook_alterations_do_not_make_a_quotation_altered() -> None:
    """A bracketed first letter and an ellipsis are the conventions, not defects.

    A checker without these rules reports a defect on an honest quotation, which
    is the failure mode this module exists to avoid.
    """
    finding = _only(
        'As the Court put it, "[w]here a complaint pleads facts that are merely consistent '
        "with a defendant's liability, it stops short of the line . . . of entitlement to "
        'relief."'
    )

    assert finding.outcome is QuotationOutcome.VERBATIM


def test_an_editorial_parenthetical_is_not_claimed_page_text() -> None:
    """`(internal quotation marks omitted)` is the quoter's note, not the court's words."""
    finding = _only(
        'It said a complaint "must contain sufficient factual matter, accepted as true, to '
        'state a claim to relief that is plausible on its face" (internal quotation marks omitted).'
    )

    assert finding.outcome is QuotationOutcome.VERBATIM


def test_substituted_words_are_altered_and_are_named() -> None:
    """The finding has to say which words differ, or a reviewer cannot check it."""
    finding = _only(
        'The Court held a complaint must "contain sufficient factual detail, accepted as '
        'accurate, to state a claim to relief that is plausible on its face."'
    )

    assert finding.outcome is QuotationOutcome.ALTERED
    assert finding.is_defect
    differing = {pair for pair in finding.differences if pair[0] != pair[1]}
    assert ("detail", "matter") in differing
    assert ("accurate", "true") in differing


def test_a_quotation_absent_from_the_page_asserts_nothing() -> None:
    """Absence may only mean the pinpoint is wrong, so it is not an alteration."""
    finding = _only(
        'The Court explained that "the pleading standard requires a showing of probable '
        'success at trial before discovery may commence."'
    )

    assert finding.outcome is QuotationOutcome.NOT_ON_PAGE
    assert not finding.is_defect


def test_a_short_quotation_is_uncheckable() -> None:
    """A few common words locate nothing, so matching them would ground a fiction."""
    finding = _only('The court called it a "claim to relief" and moved on.')

    assert finding.outcome is QuotationOutcome.UNCHECKABLE
    assert not finding.is_defect


@pytest.mark.parametrize(
    "citing",
    [
        "He said “accepted as true, to state a claim to relief that is plausible” today.",
        'He said "accepted as true, to state a claim to relief that is plausible" today.',
    ],
)
def test_curly_and_straight_quotation_marks_are_both_found(citing: str) -> None:
    """Two renderings of the same brief must not disagree about what was quoted."""
    (finding,) = check_quotations(PAGE, citing)

    assert finding.outcome is QuotationOutcome.VERBATIM


def test_quotation_spans_index_the_citing_text() -> None:
    """A finding has to point at the passage in the brief that produced it."""
    citing = 'The Court held that a complaint must "state a claim to relief that is plausible on its face."'

    ((quoted, span),) = find_quotations(citing)

    assert citing[span.start : span.end] == quoted


def test_every_fragment_must_ground_not_merely_one() -> None:
    """An ellipsis joins claims about two passages, and both are being asserted."""
    finding = check_quotation(
        PAGE,
        "accepted as true, to state a claim to relief . . . requires proof beyond reasonable doubt",
        Span(0, 10),
    )

    assert finding.outcome is QuotationOutcome.NOT_ON_PAGE
