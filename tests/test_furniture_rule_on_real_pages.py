"""Regression tests for the furniture rule, on pages taken from a real filing.

The unit tests elsewhere build documents by hand, which proves the rule does
what it says on the shapes it was written for. It does not answer the question
that matters: on a real page, is everything the rule throws away actually
noise, and is everything it keeps actually content?

`tests/fixtures/furniture_pages.json` holds every text item Docling produced
for two pages of one filing -- text, label, content layer, page, and bounding
box. They carry a page number Docling labelled `page_footer` on one page and
`text` on the other, which is the case the rule exists for.

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

from mellea_lrc.preprocessing.repeated_furniture import reclassify_repeated_furniture  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "furniture_pages.json"
SOURCE = "azd-487494839"


def _load() -> DoclingDocument:
    """Rebuild a Docling document from the recorded items of one filing."""
    recorded = next(entry for entry in json.loads(FIXTURE.read_text()) if entry["source"] == SOURCE)
    document = DoclingDocument(name=SOURCE)
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


def _removed(document: DoclingDocument) -> list[str]:
    """The text of every item the rule moves out of the body."""
    before = {id(item) for item in document.texts if item.content_layer is ContentLayer.FURNITURE}
    reclassify_repeated_furniture(document)
    return [
        item.text
        for item in document.texts
        if item.content_layer is ContentLayer.FURNITURE and id(item) not in before
    ]


def test_the_furniture_rule_removes_the_inconsistent_page_number() -> None:
    """Docling called this footer `page_footer` on one page and `text` on others.

    The page number is the same string in the same box every time. Taking the
    label from the page Docling got right is what makes the rest recoverable.
    """
    assert _removed(_load()) == ["1"]


def test_the_furniture_rule_leaves_a_document_with_no_labelled_furniture_alone() -> None:
    """Without a correctly labelled example there is no evidence to reason from."""
    document = _load()
    for item in document.texts:
        if item.label.value in ("page_header", "page_footer"):
            item.label = DocItemLabel.TEXT

    assert _removed(document) == []
