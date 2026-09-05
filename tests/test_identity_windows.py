"""Tests for the windows a citation's fields may be read from."""

from __future__ import annotations

from mellea_lrc.core.citations import FullCaseCitation
from mellea_lrc.core.spans import Span
from mellea_lrc.extraction import ExtractedCitation
from mellea_lrc.validation.identity.windows import MAX_NAME_CHARS, windows_for


def _cite(
    cid: str, text: str, name: str, locator: str, *, colocation_id: str | None = None
) -> ExtractedCitation:
    start = text.index(name)
    loc = text.index(locator)
    return ExtractedCitation(
        citation_id=cid,
        full_span=Span(start, loc + len(locator)),
        locator_span=Span(loc, loc + len(locator)),
        matched_text=locator,
        citation=FullCaseCitation(),
        colocation_id=colocation_id,
    )


def test_the_name_window_runs_from_the_previous_citation_and_the_parenthetical_to_the_next() -> None:
    text = "Brown v. Board, 347 U.S. 483 (1954). Later, Smith v. Jones, 1 F.3d 2 (9th Cir. 1990); Roe v. Wade, 410 U.S. 113 (1973)."
    brown = _cite("a", text, "Brown v. Board", "347 U.S. 483")
    smith = _cite("b", text, "Smith v. Jones", "1 F.3d 2")
    roe = _cite("c", text, "Roe v. Wade", "410 U.S. 113")
    windows = windows_for(smith, (brown, smith, roe), len(text))
    assert text[windows.name.start : windows.name.end] == " (1954). Later, Smith v. Jones, "
    assert text[windows.parenthetical.start : windows.parenthetical.end] == " (9th Cir. 1990); Roe v. Wade, "


def test_a_parallel_citation_shares_one_name_window_and_reads_past_its_neighbour() -> None:
    text = "See Ashcroft v. Iqbal, 556 U.S. 662, 129 S. Ct. 1937 (2009); Twombly, 550 U.S. 544 (2007)."
    first = _cite("a", text, "Ashcroft v. Iqbal", "556 U.S. 662", colocation_id="g")
    second = _cite("b", text, "Ashcroft v. Iqbal", "129 S. Ct. 1937", colocation_id="g")
    twombly = _cite("c", text, "Twombly", "550 U.S. 544")
    cites = (first, second, twombly)
    for member in (first, second):
        windows = windows_for(member, cites, len(text))
        assert text[windows.name.start : windows.name.end] == "See Ashcroft v. Iqbal, "
    assert text[windows_for(first, cites, len(text)).parenthetical.start :].startswith(
        ", 129 S. Ct. 1937 (2009); "
    )
    assert text[windows_for(second, cites, len(text)).parenthetical.start :].startswith(" (2009); ")
    assert windows_for(second, cites, len(text)).parenthetical.end == text.index("550 U.S. 544")


def test_the_name_window_is_capped_when_no_citation_precedes() -> None:
    text = "x" * 1000 + " Brown v. Board, 347 U.S. 483 (1954)."
    brown = _cite("a", text, "Brown v. Board", "347 U.S. 483")
    windows = windows_for(brown, (brown,), len(text))
    assert windows.name.end - windows.name.start == MAX_NAME_CHARS
    assert windows.parenthetical.end == len(text)
