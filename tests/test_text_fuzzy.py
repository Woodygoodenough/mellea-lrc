"""Tests for finding a short string in a window that may be damaged."""

from __future__ import annotations

import pytest

from mellea_lrc.text import MatchMethod, contains, find_all, find_word, normalize


def test_an_exact_string_is_found_at_every_place_it_occurs() -> None:
    window = "See Reyes v. Pac. Bell, and again Reyes v. Pac. Bell, 1 F.3d 2."
    matches = find_all("Reyes v. Pac. Bell", window)
    assert [m.method for m in matches] == [MatchMethod.EXACT, MatchMethod.EXACT]
    assert [window[m.start : m.end] for m in matches] == ["Reyes v. Pac. Bell"] * 2
    assert all(m.score == 1.0 for m in matches)


@pytest.mark.parametrize(
    ("needle", "window"),
    [
        ("Reyes v. Pac. Bell", "reyes v.  pac. bell"),
        ("Bell Atl. Corp. v. Twombly", "Bell Atl. Corp. v.\nTwombly"),
        ("Int'l Bhd.", "Int’l Bhd."),
        ("Davila-Gonzalez", "Dávila–González"),
    ],
)
def test_case_accents_quotes_dashes_and_spacing_are_not_differences(needle: str, window: str) -> None:
    matches = find_all(needle, f"before {window} after")
    assert len(matches) == 1
    assert matches[0].method is MatchMethod.NORMALIZED
    assert f"before {window} after"[matches[0].start : matches[0].end] == window


def test_one_wrong_letter_is_still_the_same_string() -> None:
    window = "Rufo v. Inmates of Suffock County Jail, 502 U.S. 367 (1992)."
    matches = find_all("Rufo v. Inmates of Suffolk County Jail", window)
    assert len(matches) == 1
    assert matches[0].method is MatchMethod.FUZZY
    assert matches[0].text == "Rufo v. Inmates of Suffock County Jail,"
    assert matches[0].score > 0.9


def test_a_word_the_converter_split_is_still_the_same_string() -> None:
    window = "Reyes v. Pac ific Bell, 1 F.3d 2."
    matches = find_all("Reyes v. Pacific Bell", window)
    assert len(matches) == 1
    assert matches[0].text.startswith("Reyes v. Pac ific Bell")


def test_a_different_name_is_not_found() -> None:
    window = "Smith v. Williams, 1 F.3d 2 (9th Cir. 2000)."
    assert find_all("Smith v. Jones", window) == ()
    assert not contains("Galeana v. Galeana", window)


def test_blank_inputs_find_nothing() -> None:
    assert find_all("", "anything") == ()
    assert find_all("  ", "anything") == ()
    assert find_all("Smith", "") == ()


def test_overlapping_fuzzy_candidates_reduce_to_the_best() -> None:
    window = "In Bell Atlantic Corp. v. Twombly the Court held."
    matches = find_all("Bell Atlantic Corp v Twombly", window)
    assert len(matches) == 1
    assert matches[0].text == "Bell Atlantic Corp. v. Twombly"


@pytest.mark.parametrize(
    ("word", "window", "expected_text"),
    [
        ("Suffolk", "Inmates of Suffock County Jail", "Suffock"),
        ("Twombly", "Corp. v. Twombly,", "Twombly,"),
        ("twombly", "Corp. v. Twombly,", "Twombly,"),
    ],
)
def test_a_word_is_found_with_a_letter_wrong_or_punctuation_attached(
    word: str, window: str, expected_text: str
) -> None:
    matches = find_word(word, window)
    assert matches
    assert matches[0].text == expected_text


def test_a_short_word_must_match_exactly() -> None:
    assert find_word("Cox", "Colgate v. Cox") and find_word("Cox", "Colgate v. Cox")[0].text == "Cox"
    assert find_word("Cox", "Colgate v. Fox") == ()


def test_normalize_folds_what_a_reader_ignores() -> None:
    assert normalize("  Dávila–González “Inc.” ") == 'davila-gonzalez "inc."'
