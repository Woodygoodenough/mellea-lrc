"""Tests for the statute-pattern relaxations, which the pipeline does not use.

These exercise `statutes/exploratory_tokenizer.py`, a record of a measurement
rather than a component. Nothing in the citation pipeline imports it: the case
extractor relaxes case patterns and leaves law patterns exactly as eyecite
generates them. See that module's docstring for why.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest
from eyecite import get_citations

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.experimental.relaxed_eyecite_extractor import extract_relaxed_citations, relaxed_tokenizer
from mellea_lrc.statutes.exploratory_tokenizer import exploratory_statute_tokenizer


def _sections(text: str) -> set[str]:
    """Statute title and section, as this tokenizer reads them."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        found = get_citations(text, tokenizer=exploratory_statute_tokenizer())
    return {
        f"{c.groups.get('title')} U.S.C. § {c.groups.get('section')}"
        for c in found
        if c.groups.get("section")
    }


def test_a_statute_section_may_carry_a_letter_on_its_digits() -> None:
    """eyecite's section pattern allows digits, dots, dashes and colons only.

    A section written `2000e-2` or `1681g` therefore matches nothing at all --
    not a degraded parse but no citation, so a checker never sees it. Those two
    are Title VII and the Fair Credit Reporting Act.
    """
    text = "under 42 U.S.C. § 2000e-2(a)(1), 15 U.S.C. § 1681g, 29 U.S.C. § 794a, and 15 U.S.C. § 77l"

    assert _sections(text) == {
        "42 U.S.C. § 2000e-2",
        "15 U.S.C. § 1681g",
        "29 U.S.C. § 794a",
        "15 U.S.C. § 77l",
    }


def test_a_statute_reporter_may_be_written_without_its_closing_period() -> None:
    """`42 U.S.C § 12132` and `29 U.S.C.A § 2612` are both written that way."""
    assert _sections("on the basis of that disability. 42 U.S.C § 12132.") == {"42 U.S.C. § 12132"}
    assert _sections("leave pursuant to 29 U.S.C.A § 2612 (a)(1) for") == {"29 U.S.C. § 2612"}


def test_the_ordinary_section_forms_are_unchanged() -> None:
    text = "under 42 U.S.C. § 1983, 28 U.S.C. § 636(b)(1)(A), and 42 U.S.C. § 12112"

    assert _sections(text) == {"42 U.S.C. § 1983", "28 U.S.C. § 636", "42 U.S.C. § 12112"}


@pytest.mark.parametrize("text", ["42 U.S.C. § 1983 and the rule", "42 U.S.C. § 1983. Next sentence"])
def test_a_section_does_not_absorb_the_word_that_follows_it(text: str) -> None:
    assert _sections(text) == {"42 U.S.C. § 1983"}


def test_the_citation_pipeline_does_not_use_any_of_this() -> None:
    """The case extractor leaves law patterns exactly as eyecite generates them.

    Statute checking is a domain-learning exercise that has not settled how a
    provision should be represented or which jurisdictions to take in what
    order. Until it does, the citation results must not depend on it.
    """
    text = "brought under 42 U.S.C. § 2000e-2(a)(1) for discrimination"

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        pipeline = get_citations(text, tokenizer=relaxed_tokenizer())

    assert not [c for c in pipeline if c.groups.get("section") == "2000e-2"]
    assert _sections(text) == {"42 U.S.C. § 2000e-2"}


def test_case_extraction_is_identical_either_way() -> None:
    """Whatever the statute patterns do, the case citations must not move."""
    text = "See Doe v. Colgate Univ. , 2016 WL1448829, at *2 (N.D.N.Y. 2016) and 410 U.S. 113 (1973)"

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        widened = get_citations(text, tokenizer=exploratory_statute_tokenizer())
    baseline = {
        f"{c.citation.volume} {c.citation.reporter} {c.citation.page}"
        for c in extract_relaxed_citations(text).citations
        if isinstance(c.citation, FullCaseCitation)
    }

    assert baseline == {
        f"{c.groups.get('volume')} {c.groups.get('reporter')} {c.groups.get('page')}"
        for c in widened
        if c.groups.get("page") and c.groups.get("volume")
    }
