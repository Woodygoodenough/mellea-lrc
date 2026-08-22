"""Tests for carrying benchmark annotations onto a corrected rendering."""

from __future__ import annotations

from scripts.corpus.regenerate import Alignment, _carry_over

# The real shape of the change: a margin block sits between the two halves of a
# sentence, and removing it pulls everything after it earlier.
WITH_MARGIN = "See Ashcroft v.\n\n1\n\n2\n\n3\n\nIqbal , 556 U.S. 662, 678 (2009)."
WITHOUT_MARGIN = "See Ashcroft v.\n\nIqbal , 556 U.S. 662, 678 (2009)."


def _record(text: str, source: str = WITH_MARGIN) -> dict:
    start = source.index(text)
    return {
        "id": f"022:{start}-{start + len(text)}",
        "document": "022.txt",
        "matched_text": text,
        "span": {"start": start, "end": start + len(text)},
    }


def test_a_span_after_the_removal_is_moved_not_lost() -> None:
    """This is the case the whole re-derivation exists for."""
    alignment = Alignment.between(WITH_MARGIN, WITHOUT_MARGIN)
    start = WITH_MARGIN.index("556 U.S. 662")

    moved = alignment.project_span(start, start + len("556 U.S. 662"))

    assert moved is not None
    assert WITHOUT_MARGIN[moved[0] : moved[1]] == "556 U.S. 662"
    assert moved[0] < start


def test_a_span_before_the_removal_does_not_move() -> None:
    """Only text after a removal shifts; the alignment must not disturb the rest."""
    alignment = Alignment.between(WITH_MARGIN, WITHOUT_MARGIN)

    assert alignment.project_span(0, 3) == (0, 3)


def test_an_offset_inside_a_removed_region_has_no_answer() -> None:
    """Guessing here would silently relocate an annotation onto unrelated text."""
    alignment = Alignment.between(WITH_MARGIN, WITHOUT_MARGIN)

    assert alignment.project(WITH_MARGIN.index("\n\n1\n\n") + 2) is None


def test_the_carried_identifier_is_restated_in_the_new_coordinates() -> None:
    """An id encoding stale offsets would address the old rendering."""
    carried, failures = _carry_over(WITH_MARGIN, WITHOUT_MARGIN, [_record("556 U.S. 662")])

    assert failures == 0
    (record,) = carried
    assert record["id"] == f"022:{record['span']['start']}-{record['span']['end']}"
    assert WITHOUT_MARGIN[record["span"]["start"] : record["span"]["end"]] == "556 U.S. 662"


def test_an_annotation_whose_text_did_not_survive_is_reported() -> None:
    """Verifying the text at the projected span is what makes silence impossible.

    An offset can project cleanly and still land on the wrong thing when the
    rendering changed nearby. Checking the string is cheap and turns a
    misplaced annotation into a reported one.
    """
    scrambled = WITHOUT_MARGIN.replace("556 U.S. 662", "556 U.S. 999")

    carried, failures = _carry_over(WITH_MARGIN, scrambled, [_record("556 U.S. 662")])

    assert carried == []
    assert failures == 1


def test_an_unchanged_rendering_carries_everything_unmoved() -> None:
    """The degenerate case has to be exact, since most documents have no margin."""
    records = [_record("556 U.S. 662"), _record("Ashcroft")]

    carried, failures = _carry_over(WITH_MARGIN, WITH_MARGIN, records)

    assert failures == 0
    assert [c["span"] for c in carried] == [r["span"] for r in records]
