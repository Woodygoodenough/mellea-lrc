"""Regression tests for the layout rules, on pages taken from real filings.

The unit tests elsewhere build documents by hand, which proves the rules do
what they say on the shapes they were written for. It does not answer the
question that matters: on a real page, is everything these rules throw away
actually noise, and is everything they keep actually content?

`tests/fixtures/page_layout.json` holds every text item Docling produced for
four pages of two filings -- text, label, content layer, page, and bounding
box. Two pages carry a citation split by a line-number margin; two carry a
page number Docling labelled `page_footer` once and `text` on the other pages.

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
from docling_core.types.doc.labels import DocItemLabel  # noqa: E402

from mellea_lrc.preprocessing.margin_line_numbers import reclassify_margin_line_numbers  # noqa: E402
from mellea_lrc.preprocessing.repeated_furniture import reclassify_repeated_furniture  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "page_layout.json"


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


def test_the_furniture_rule_removes_the_inconsistent_page_number() -> None:
    """Docling called this footer `page_footer` on one page and `text` on others.

    The page number is the same string in the same box every time. Taking the
    label from the page Docling got right is what makes the rest recoverable.
    """
    document = _load("azd-487494839")

    removed = _removed(document, reclassify_repeated_furniture)

    assert removed == ["1"]


def test_the_furniture_rule_leaves_a_document_with_no_labelled_furniture_alone() -> None:
    """Without a correctly labelled example there is no evidence to reason from."""
    document = _load("022")
    for item in document.texts:
        if item.label.value in ("page_header", "page_footer"):
            item.label = DocItemLabel.TEXT

    assert _removed(document, reclassify_repeated_furniture) == []


def test_the_two_rules_together_remove_only_numbers_and_furniture() -> None:
    """Run in sequence, as preprocessing runs them, nothing else goes."""
    for source in ("022", "azd-487494839"):
        document = _load(source)
        removed = _removed(document, reclassify_margin_line_numbers)
        removed += _removed(document, reclassify_repeated_furniture)

        for text in removed:
            assert (text or "").strip().isdigit(), f"{source}: removed non-numeric {text!r}"
