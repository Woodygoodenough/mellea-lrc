"""JSON round-trip support for the identity stage's output.

A record serializes as three things side by side: the citation as extraction
produced it, the citation as validation now reads it, and the log of every
change between them with the trace node each rests on. The trace itself is
written with the same node encoding the validated-document artifact uses.
"""

from __future__ import annotations

from collections.abc import Mapping

from mellea_lrc.serialization._json import JsonValue, require_list, require_mapping, serialize_dataclass
from mellea_lrc.serialization.extracted_document import (
    SCHEMA_VERSION,
    _deserialize_citation,
    _optional_string,
    _require_artifact,
    _required_string,
    deserialize_extracted_document,
    serialize_extracted_document,
)
from mellea_lrc.serialization.validated_document import _deserialize_node
from mellea_lrc.validation.identity.stage import IdentifiedDocument
from mellea_lrc.validation.record import CitationRecord, Correction, Resolution

_ARTIFACT_TYPE = "identified_document"


def serialize_identified_document(document: IdentifiedDocument) -> dict[str, JsonValue]:
    """Project one ``IdentifiedDocument`` into a recoverable JSON artifact."""
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": _ARTIFACT_TYPE,
        "source": serialize_extracted_document(document.source),
        "records": [_serialize_record(record) for record in document.records],
    }


def deserialize_identified_document(payload: Mapping[str, object]) -> IdentifiedDocument:
    """Recover one ``IdentifiedDocument`` from its serialized artifact."""
    _require_artifact(payload, artifact_type=_ARTIFACT_TYPE)
    source = deserialize_extracted_document(require_mapping(payload.get("source"), name="source"))
    records = require_list(payload.get("records"), name="records")
    if len(records) != len(source.citations):
        msg = "Records must exactly match extracted citations"
        raise ValueError(msg)
    return IdentifiedDocument(
        source=source,
        records=tuple(
            _deserialize_record(require_mapping(value, name="record"), extracted)
            for value, extracted in zip(records, source.citations, strict=True)
        ),
    )


def _serialize_record(record: CitationRecord) -> dict[str, JsonValue]:
    # The current reading is encoded like an extracted citation so one decoder
    # serves both; its spans and identifier are the source's, which never change.
    return {
        "citation_id": record.citation_id,
        "citation": {
            "citation_type": record.citation.kind.value,
            **serialize_dataclass(record.citation),
        },
        "authority_id": record.authority_id,
        "resolution": serialize_dataclass(record.resolution) if record.resolution is not None else None,
        "corrections": [serialize_dataclass(correction) for correction in record.corrections],
        "nodes": [
            {"node_type": type(node).__name__, **serialize_dataclass(node)} for node in record.trace.nodes
        ],
    }


def _deserialize_record(payload: Mapping[str, object], extracted: object) -> CitationRecord:
    from mellea_lrc.extraction.types import ExtractedCitation

    if not isinstance(extracted, ExtractedCitation):
        msg = "A record must be paired with its extracted citation"
        raise TypeError(msg)
    if payload.get("citation_id") != extracted.citation_id:
        msg = "Records must preserve extracted citation order"
        raise ValueError(msg)
    current = _deserialize_citation(
        {
            "citation_id": extracted.citation_id,
            "full_span": serialize_dataclass(extracted.full_span),
            "locator_span": serialize_dataclass(extracted.locator_span),
            "matched_text": extracted.matched_text,
            "citation": require_mapping(payload.get("citation"), name="record.citation"),
        }
    ).citation
    record = CitationRecord(
        source=extracted,
        citation=current,
        authority_id=_optional_string(payload.get("authority_id"), name="record.authority_id"),
    )
    for node_payload in require_list(payload.get("nodes"), name="record.nodes"):
        record.append(_deserialize_node(node_payload))
    resolution = payload.get("resolution")
    if resolution is not None:
        fields = require_mapping(resolution, name="record.resolution")
        record.resolve(
            Resolution(
                cluster_id=_optional_string(fields.get("cluster_id"), name="record.resolution.cluster_id"),
                case_name=_optional_string(fields.get("case_name"), name="record.resolution.case_name"),
                date_filed=_optional_string(fields.get("date_filed"), name="record.resolution.date_filed"),
                court_id=_optional_string(fields.get("court_id"), name="record.resolution.court_id"),
                node_id=_required_string(fields.get("node_id"), name="record.resolution.node_id"),
            )
        )
    record.corrections = tuple(
        Correction(
            field=_required_string(item.get("field"), name="record.corrections.field"),
            before=item.get("before"),
            after=item.get("after"),
            made_by=_required_string(item.get("made_by"), name="record.corrections.made_by"),
            reason=_required_string(item.get("reason"), name="record.corrections.reason"),
            node_id=_required_string(item.get("node_id"), name="record.corrections.node_id"),
        )
        for item in (
            require_mapping(value, name="record.corrections")
            for value in require_list(payload.get("corrections"), name="record.corrections")
        )
    )
    return record
