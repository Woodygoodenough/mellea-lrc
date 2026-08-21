"""Tests for blanking the margin line-number gutter of pleading paper."""

from __future__ import annotations

import pytest

from mellea_lrc.experimental.line_number_gutter import (
    blank_line_number_gutters,
    gutter_runs,
)


def _gutter(first: int, last: int) -> str:
    return "".join(f"{n}\n\n" for n in range(first, last + 1))


def test_a_citation_split_by_the_gutter_is_made_whole() -> None:
    """This is the case the rule exists for.

    `214 F.3d 1058` survived extraction intact; a column of unrelated integers
    was emitted between its halves. Nothing about the citation is repaired here
    -- only the interruption is removed.
    """
    text = f"Advanced Textile , 214 F.3d\n\n{_gutter(1, 28)}1058 (9th Cir. 2000)"

    assert "214 F.3d" in blank_line_number_gutters(text)
    assert "1058 (9th Cir. 2000)" in blank_line_number_gutters(text)
    assert blank_line_number_gutters(text).split() == [
        "Advanced",
        "Textile",
        ",",
        "214",
        "F.3d",
        "1058",
        "(9th",
        "Cir.",
        "2000)",
    ]


def test_no_offset_moves() -> None:
    """Blanking rather than deleting is what makes this safe to apply early.

    Spans are the project's join between extraction, validation and reporting.
    A rule that shortened the text would invalidate every one of them.
    """
    text = f"before\n\n{_gutter(3, 12)}after"

    assert len(blank_line_number_gutters(text)) == len(text)
    assert blank_line_number_gutters(text).index("after") == text.index("after")


def test_a_numbered_list_is_not_a_gutter() -> None:
    """The pattern must not eat content that happens to begin with integers."""
    text = "Requirements:\n\n1\n\nservice\n\n2\n\nnotice\n\n3\n\nfiling\n\n"

    assert gutter_runs(text) == ()
    assert blank_line_number_gutters(text) == text


def test_numbers_that_do_not_count_up_are_left_alone() -> None:
    """A margin counts by one. Anything else is data and must survive."""
    scattered = "".join(f"{n}\n\n" for n in (4, 9, 2, 7, 11, 3, 15))
    text = f"totals\n\n{scattered}end"

    assert gutter_runs(text) == ()


def test_a_short_ascending_run_is_left_alone() -> None:
    """Reaching a plausible gutter length is required, not merely starting like one."""
    text = f"steps\n\n{_gutter(1, 4)}end"

    assert gutter_runs(text) == ()


@pytest.mark.parametrize("page", ["662", "1058"])
def test_a_reporter_page_is_never_mistaken_for_a_gutter(page: str) -> None:
    """Two digits is the limit precisely so that pages stay out of reach."""
    text = f"550 U.S.\n\n{page}\n\n" * 8

    assert gutter_runs(text) == ()


def test_every_run_in_a_document_is_blanked() -> None:
    """Pleading paper repeats the margin on every page."""
    text = f"one\n\n{_gutter(1, 28)}two\n\n{_gutter(1, 28)}three"

    assert len(gutter_runs(text)) == 2
    assert blank_line_number_gutters(text).split() == ["one", "two", "three"]
