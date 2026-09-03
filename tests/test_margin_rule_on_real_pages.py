"""Regression tests for the margin rule, on pages taken from a real filing.

The unit tests elsewhere build documents by hand, which proves the rule does
what it says on the shapes it was written for. It does not answer the question
that matters: on a real page, is everything the rule throws away actually
noise, and is everything it keeps actually content?

`tests/fixtures/margin_pages.json` holds every text item Docling produced for
two pages of one filing -- text, label, content layer, page, and bounding box.
The two carry a citation split by a line-number margin, which is the case the
rule exists for.

The assertions are exact counts and exact strings. A rule that starts removing
more, or less, or something different, fails here rather than in a corpus run
nobody remembered to repeat.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("docling_core", reason="Docling is an optional preprocessing dependency")

from docling_core.types.doc.base import BoundingBox, CoordOrigin  # noqa: E402
from docling_core.types.doc.common.content_layer import ContentLayer  # noqa: E402
from docling_core.types.doc.common.reference import ProvenanceItem  # noqa: E402
from docling_core.types.doc.document import DoclingDocument  # noqa: E402

from mellea_lrc.preprocessing.margin_line_numbers import reclassify_margin_line_numbers  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "margin_pages.json"


def _load(source: str) -> DoclingDocument:
    """Rebuild a Docling document from the recorded items of one filing."""
    recorded = next(entry for entry in json.loads(FIXTURE.read_text()) if entry["source"] == source)
    document = DoclingDocument(name=source)
    for item in recorded["items"]:
        document.add_text(
            label=item["label"],
            text=item["text"],
            content_layer=ContentLayer(item["layer"]),
            prov=ProvenanceItem(
                page_no=item["page"],
                bbox=BoundingBox(
                    l=item["l"],
                    t=item["t"],
                    r=item["r"],
                    b=item["b"],
                    coord_origin=CoordOrigin.BOTTOMLEFT,
                ),
                charspan=(0, len(item["text"] or "")),
            ),
        )
    return document


def _removed(document: DoclingDocument, rule) -> list[str]:
    """The text of every item a rule moves out of the body."""
    before = {id(item) for item in document.texts if item.content_layer is ContentLayer.FURNITURE}
    rule(document)
    return [
        item.text
        for item in document.texts
        if item.content_layer is ContentLayer.FURNITURE and id(item) not in before
    ]


def test_the_margin_rule_removes_line_numbers_and_nothing_else() -> None:
    """Every removed item is a line number; no prose is taken with them."""
    document = _load("022")

    removed = _removed(document, reclassify_margin_line_numbers)

    assert len(removed) == 56
    assert sorted(set(removed), key=int) == [str(n) for n in range(1, 29)]


def test_the_citation_the_margin_split_survives_intact() -> None:
    """Page 7 ends at `214 F.3d`; page 8 opens with its own margin, then `1058`."""
    document = _load("022")
    reclassify_margin_line_numbers(document)

    text = document.export_to_text()

    assert "214 F.3d\n\n1058 (9th Cir. 2000)" in text
    assert "214 F.3d\n\n1\n\n2" not in text


def test_the_prose_of_those_pages_is_untouched() -> None:
    """The rule must cost nothing on pages it also cleans."""
    document = _load("022")
    before = [item.text for item in document.texts if item.content_layer is ContentLayer.BODY]

    reclassify_margin_line_numbers(document)
    after = {item.text for item in document.texts if item.content_layer is ContentLayer.BODY}

    kept = [text for text in before if not (text or "").strip().isdigit()]
    assert all(text in after for text in kept)
