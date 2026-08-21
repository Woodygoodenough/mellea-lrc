"""Tests for reading LePhantomCite rows into citation-keyed records."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluations.lephantomcite.dataset import (
    HallucinationType,
    LabelledCitation,
    load_excerpts,
    locator_key,
)


def _write(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "eval.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("cited", "expected"),
    [
        ("556 U.S. 662", "556|us|662"),
        ("798 F. Supp. 2d 1215", "798|fsupp2d|1215"),
        ("798 F.Supp.2d 1215", "798|fsupp2d|1215"),
        ("755 N.E.2d 589, 591 (Ind. 2001)", "755|ne2d|589"),
        ("755 N.E.2d at 598", "755|ne2d|598"),
        ("no locator here", None),
    ],
)
def test_locator_key_normalizes_surface_variation(cited: str, expected: str | None) -> None:
    """Two spellings of one reporter reduce to one key; a short form keeps its pin."""
    assert locator_key(cited) == expected


def test_labels_are_keyed_to_the_citation_not_the_span(tmp_path: Path) -> None:
    """A defect recorded against a citation reaches that citation's record."""
    path = _write(
        tmp_path,
        [
            {
                "filename": "a.pdf",
                "text": "See 755 N.E.2d 589, 591 (Ind. 2001).",
                "citations_in_segment": ["755 N.E.2d 589, 591 (Ind. 2001)", "556 U.S. 662"],
                "list_hallucination_types": {"755 N.E.2d 589, 591 (Ind. 2001)": ["wrong_pincite"]},
            }
        ],
    )

    (excerpt,) = load_excerpts(path)

    labelled, sound = excerpt.citations
    assert labelled.types == frozenset({HallucinationType.WRONG_PINCITE})
    assert labelled.is_semantic_defect
    assert not labelled.is_identity_defect
    assert sound.types == frozenset()
    assert not sound.is_defective
    assert excerpt.defective == (labelled,)


def test_optional_spans_are_not_labels(tmp_path: Path) -> None:
    """The benchmark's own evaluator excludes `optional`, so it is not a defect."""
    path = _write(
        tmp_path,
        [
            {
                "filename": "a.pdf",
                "text": "See 556 U.S. 662.",
                "citations_in_segment": ["556 U.S. 662"],
                "list_hallucination_types": {"556 U.S. 662": ["optional"]},
            }
        ],
    )

    (excerpt,) = load_excerpts(path)

    assert excerpt.defective == ()


def test_a_row_without_labels_reads_as_sound(tmp_path: Path) -> None:
    """Twenty-four released rows omit the label field entirely."""
    path = _write(
        tmp_path,
        [{"filename": "a.pdf", "text": "See 556 U.S. 662.", "citations_in_segment": ["556 U.S. 662"]}],
    )

    (excerpt,) = load_excerpts(path)

    assert len(excerpt.citations) == 1
    assert excerpt.defective == ()


def test_identity_and_semantic_defects_are_separated() -> None:
    """A citation carrying both kinds counts as semantic, not identity-only."""
    both = LabelledCitation(
        cited_text="556 U.S. 662",
        locator_key="556|us|662",
        types=frozenset({HallucinationType.CASE_NAME_MISMATCH, HallucinationType.MISQUOTE}),
    )

    assert both.is_semantic_defect
    assert not both.is_identity_defect


def test_excerpt_ids_are_unique_across_repeated_filenames(tmp_path: Path) -> None:
    """One brief is split into several rows, so the filename alone is not an id."""
    row: dict[str, object] = {"filename": "a.pdf", "text": "x", "citations_in_segment": []}
    path = _write(tmp_path, [dict(row), dict(row)])

    first, second = load_excerpts(path)

    assert first.excerpt_id != second.excerpt_id
