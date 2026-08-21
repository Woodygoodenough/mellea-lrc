"""Tests for what the layout-tolerant tokenizer will and will not join.

eyecite joins volume, reporter and page with a literal single space, so any
damage to that separator makes the citation vanish rather than parse badly --
and a citation that vanishes is absent from the ledger, so a filing full of
them earns a clean bill instead of an incomplete one.

Damage runs in both directions. Extraction leaves doubled spaces and line
breaks; some documents carry the opposite, a missing space, either from OCR or
from a word processor that wrote `846F.2d746` into its own text layer.
Relaxing the joins covers both with one change.

The bound matters as much as the relaxation. Whitespace that may be crossed
stops at one newline: a citation can be broken across a line or a page, but
never across a blank line, and relaxing that far produced this project's only
extraction false positive.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from mellea_lrc.experimental.relaxed_eyecite_extractor import extract_relaxed_citations
from mellea_lrc.extraction import extract_from_plain_text


def _matched(text: str) -> list[str]:
    # eyecite writes overlap diagnostics to stdout on some inputs.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        document = extract_relaxed_citations(text)
    return [item.matched_text for item in document.citations]


def _baseline(text: str) -> list[str]:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        document = extract_from_plain_text(text)
    return [item.matched_text for item in document.citations]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The court relied on 846F.2d746 for that proposition.", "846F.2d746"),
        ("Reversed at 347U.S.483 (1954).", "347U.S.483"),
        ("See Ashcroft v. Iqbal, 556U.S.662, 678 (2009).", "556U.S.662"),
    ],
)
def test_a_glued_citation_is_recovered(text: str, expected: str) -> None:
    """A missing separator is damage, not absence of a citation.

    The baseline finds nothing at all in these, which is the failure mode worth
    naming: nothing downstream reports a problem because nothing downstream was
    told a citation was there.
    """
    assert _baseline(text) == []
    assert expected in _matched(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("See 550  F.3d  1000 here.", "550 F.3d 1000"),
        ("See 347 U.S.\n483 (1954).", "347 U.S.\n483"),
    ],
)
def test_separator_damage_in_the_other_direction_still_matches(text: str, expected: str) -> None:
    """Doubled spaces and a line break are the same defect seen from the other side."""
    assert expected in _matched(text)


def test_a_citation_is_never_joined_across_a_blank_line() -> None:
    """Two newlines are a block boundary, and no citation spans one.

    Allowing arbitrary whitespace joined `214 F.3d` to the `1` that opened the
    next paragraph -- the only false positive the relaxed tokenizer produced on
    false-citation-bench, and the reason the relaxation is bounded rather than
    open.
    """
    assert _matched("See 214 F.3d\n\n1 The next paragraph begins here.") == []


def test_an_ordinary_citation_is_unaffected() -> None:
    """Relaxation must not change what already worked."""
    text = "See Ashcroft v. Iqbal, 556 U.S. 662, 678 (2009)."

    assert _matched(text) == _baseline(text)
