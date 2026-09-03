"""Label Studio prediction serialization for pre-annotation."""

from dataclasses import fields
from typing import Any

from mellea_lrc.core.citations import (
    FullCaseCitation,
    FullJournalCitation,
    FullLawCitation,
    IdCitation,
    ReferenceCitation,
    ShortCaseCitation,
    SupraCitation,
    UnknownCitation,
)
from mellea_lrc.extraction.types import ExtractedCitation, ExtractedDocument

MODEL_VERSION = "eyecite-pre-annotation"


def _shallow(citation: object) -> dict[str, str | None]:
    """Each field as one string.

    `asdict` would expand `reporter` and `date` into nested dictionaries, and a
    Label Studio textarea holds text. Both render as the document wrote them.
    """
    return {
        field.name: None if getattr(citation, field.name) is None else str(getattr(citation, field.name))
        for field in fields(citation)
    }


def _field_values(item: ExtractedCitation) -> dict[str, str | None]:
    citation = item.citation
    if isinstance(citation, FullCaseCitation):
        return _shallow(citation)
    if isinstance(citation, FullLawCitation):
        return _shallow(citation)
    if isinstance(citation, FullJournalCitation):
        return _shallow(citation)
    if isinstance(citation, ShortCaseCitation):
        return _shallow(citation)
    if isinstance(citation, SupraCitation):
        return _shallow(citation)
    if isinstance(citation, IdCitation):
        return _shallow(citation)
    if isinstance(citation, ReferenceCitation):
        return _shallow(citation)
    if isinstance(citation, UnknownCitation):
        return {}
    msg = f"Unsupported citation type: {type(citation).__name__}"
    raise TypeError(msg)


def _label_result(extraction: ExtractedDocument, item: ExtractedCitation) -> dict[str, Any]:
    annotated_text = extraction.text[item.span.start : item.span.end]
    return {
        "id": item.citation_id,
        "from_name": "label",
        "to_name": "text",
        "type": "labels",
        "value": {
            "start": item.span.start,
            "end": item.span.end,
            "text": annotated_text,
            "labels": [item.citation.kind.value],
        },
    }


def _field_results(item: ExtractedCitation) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for field_name, value in _field_values(item).items():
        results.append(
            {
                "id": item.citation_id,
                "from_name": field_name,
                "to_name": "text",
                "type": "textarea",
                "value": {"text": [value if value is not None else ""]},
            }
        )
    return results


def _relation_results(extraction: ExtractedDocument) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in extraction.citations:
        if item.resolves_to is None:
            continue
        results.append(
            {
                "from_id": item.citation_id,
                "to_id": item.resolves_to,
                "type": "relation",
                "direction": "right",
            }
        )
    return results


def to_label_studio_prediction(extraction: ExtractedDocument) -> dict[str, Any]:
    """Convert a document extraction into a Label Studio prediction dict."""
    results: list[dict[str, Any]] = []
    for item in extraction.citations:
        results.append(_label_result(extraction, item))
        results.extend(_field_results(item))
    results.extend(_relation_results(extraction))

    return {
        "model_version": MODEL_VERSION,
        "score": 1.0,
        "result": results,
    }
