"""The identify command loads an extraction artifact and writes an identified one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mellea_lrc.cli import main
from mellea_lrc.extraction import extract_from_plain_text
from mellea_lrc.serialization import deserialize_identified_document, serialize_extracted_document
from mellea_lrc.validation.types import IdentityOutcome, IdentityReason, IdentityResolutionNode


def test_identify_reads_an_extraction_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = "See Bell Atl. Corp. v. Twombly, 550 U.S. 544, 555 (2007). Id. at 570."
    artifact = tmp_path / "doc.json"
    artifact.write_text(
        json.dumps(serialize_extracted_document(extract_from_plain_text(text))), encoding="utf-8"
    )

    async def fake_identify(document: object, **_kwargs: object) -> object:
        from mellea_lrc.validation.identity.stage import IdentifiedDocument, scope_node
        from mellea_lrc.validation.record import CitationRecord
        from mellea_lrc.validation.types import ValidationNodeStatus

        records = tuple(CitationRecord.from_extracted(item) for item in document.citations)
        for record in records:
            scope = record.append(scope_node(record))
            if record.is_root:
                record.append(
                    IdentityResolutionNode(
                        node_id=f"{record.citation_id}:identity_resolution",
                        status=ValidationNodeStatus.SUCCEEDED,
                        outcome=IdentityOutcome.DEFER_TO_SEARCH,
                        reason=IdentityReason.NOT_FOUND,
                        cluster_id=None,
                        record_case_name=None,
                        decided_by="rule",
                        fields=(),
                        depends_on=(scope.node_id,),
                    )
                )
        return IdentifiedDocument(source=document, records=records)

    monkeypatch.setattr("mellea_lrc.cli.identify_document", fake_identify)
    output = tmp_path / "out.json"

    assert main(["identify", "--from-artifact", str(artifact), "-o", str(output)]) == 0

    identified = deserialize_identified_document(json.loads(output.read_text(encoding="utf-8")))
    assert identified.source.text == text
    assert [record.is_root for record in identified.records] == [True, False]
    assert (
        identified.resolution_of(identified.records[1].citation_id).outcome is IdentityOutcome.DEFER_TO_SEARCH
    )
