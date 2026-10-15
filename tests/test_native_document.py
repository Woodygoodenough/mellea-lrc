"""Native documents preserve exact history and reject invalid checkpoint state."""

import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from mellea_lrc.model import (
    CaseNameKind,
    CheckpointRun,
    Document,
    FullDocketCitation,
    FullReporterCitation,
    PreprocessedDocument,
    PreprocessingMetadata,
    SourceMetadata,
    Span,
    TableOfAuthoritiesComponent,
    latest,
)
from mellea_lrc.model.citations.history import WITHDRAWN_ROOT_ID

DISCOVERY = "grow_roots.discover_root_locators"
REPORTERS = f"{DISCOVERY}.find_full_reporter_locators"
DOCKETS = f"{DISCOVERY}.find_docket_locators"
HUNTING = f"{DISCOVERY}.hunt_docket_locators"
TEXT = "Smith v. Jones, 347 U.S. 483 (1954); No. 1:24-cv-00123."


def document(text=TEXT, *, index_spans=()):
    return Document.from_preprocessed(
        PreprocessedDocument(
            text=text,
            source_metadata=SourceMetadata(path="filing.txt"),
            preprocessing_metadata=PreprocessingMetadata(),
            index_spans=index_spans,
        )
    )


def reporter(text=TEXT, *, identifier="reporter", substage=REPORTERS):
    start = text.index("347 U.S. 483")
    return FullReporterCitation.from_locator(
        citation_id=identifier,
        source=text,
        span=Span(start, start + len("347 U.S. 483")),
        substage=substage,
    )


def docket(text=TEXT, *, identifier="docket", substage=DOCKETS):
    start = text.index("No. ")
    number = "1:24-cv-00123"
    return FullDocketCitation.from_locator(
        citation_id=identifier,
        source=text,
        span=Span(start, start + 4 + len(number)),
        number_span=Span(start + 4, start + 4 + len(number)),
        substage=substage,
    )


def discovered():
    first = document().add_citation(reporter()).complete_substage(REPORTERS)
    second = first.add_citation(docket()).complete_substage(DOCKETS)
    return first, second


def test_native_roundtrip_and_every_checkpoint_preserve_complete_documents():
    first, second = discovered()
    group = second.complete_stage(DISCOVERY)
    name = group.replace_citation(
        group.citations[0].record("read_name").with_case_name(TEXT, Span(0, 14))
    ).complete_substage("read_name")
    current = name.replace_citation(
        name.citations[0].record("correct_name").with_case_name(TEXT, Span(0, 5))
    ).complete_substage("correct_name")
    final = current.complete_substage("empty_checkpoint")
    restored = Document.model_validate_json(final.model_dump_json())
    assert restored == final
    for checkpoint, expected in (
        (REPORTERS, first),
        (DOCKETS, second),
        ("read_name", name),
        ("correct_name", current),
        ("empty_checkpoint", final),
    ):
        assert restored.get_substage(checkpoint) == expected
    assert restored.get_stage(DISCOVERY) == group
    assert first.citations[0] == second.citations[0]
    assert restored.get_substage(REPORTERS).citations == first.citations
    assert [reading.quote for reading in restored.citations[0].case_name] == ["Smith v. Jones", "Smith"]
    assert restored.citations[0].get_case_name().kind is CaseNameKind.PARTIAL
    assert latest(restored.citations[0].case_name).partial == "Smith"
    assert final.source_metadata == first.source_metadata


def test_pending_changes_do_not_leak_into_completed_checkpoints():
    _, second = discovered()
    pending = second.replace_citation(
        second.citations[0].record("read_name").with_case_name(TEXT, Span(0, 14))
    )
    assert pending.get_substage(DOCKETS) == second
    assert Document.model_validate_json(pending.model_dump_json()) == pending
    with pytest.raises(ValidationError, match="Only one substage"):
        pending.replace_citation(pending.citations[1].record("another_substage"))
    with pytest.raises(ValueError, match="pending substage"):
        pending.complete_substage("different_checkpoint")


def test_native_schema_has_one_run_log_and_no_external_workflow_records():
    _, second = discovered()
    payload = second.model_dump(mode="json")
    assert payload["runs"] == [{"kind": "substage", "name": REPORTERS}, {"kind": "substage", "name": DOCKETS}]
    assert "stage_runs" not in payload and "substage_runs" not in payload
    for name in ("updates", "operations", "reporter_exact_lookup", "reporter_support_reviews"):
        assert name not in payload["citations"][0]
    assert isinstance(Document.model_json_schema(), dict)
    with pytest.raises(ValidationError, match="Extra inputs"):
        Document.model_validate({**payload, "stage_runs": []})


@pytest.mark.parametrize("boundary", [REPORTERS, DOCKETS])
def test_duplicate_completion_and_reopened_work_fail(boundary):
    _, second = discovered()
    with pytest.raises(ValueError, match="already completed"):
        second.complete_substage(boundary)
    with pytest.raises(ValueError, match="already completed"):
        second.replace_citation(second.citations[0].record(boundary))
    payload = second.model_dump(mode="json")
    payload["runs"].append({"kind": "substage", "name": boundary})
    with pytest.raises(ValidationError, match="must be unique"):
        Document.model_validate(payload)


def test_group_boundaries_require_members_in_order_and_close_optional_work():
    partial = document().complete_substage(REPORTERS)
    with pytest.raises(ValidationError, match="unfinished required"):
        partial.complete_stage(DISCOVERY)
    with pytest.raises(KeyError, match="has not run"):
        partial.get_stage(DISCOVERY)
    _, second = discovered()
    completed = second.complete_stage(DISCOVERY)
    assert completed.runs[-1] == CheckpointRun(kind="stage", name=DISCOVERY)
    with pytest.raises(ValueError, match="completed stage"):
        completed.complete_substage(HUNTING)
    with pytest.raises(ValueError, match="already completed"):
        completed.complete_stage(DISCOVERY)
    reversed_runs = document().complete_substage(DOCKETS).complete_substage(REPORTERS)
    with pytest.raises(ValidationError, match="catalog order"):
        reversed_runs.complete_stage(DISCOVERY)


def test_unknown_names_fail_and_unqualified_development_checkpoints_work():
    initial = document()
    for name in ("grow_roots.discover_root_locators.typo", "validate_roots.lookup.old"):
        with pytest.raises(ValidationError, match="Unknown substage"):
            initial.complete_substage(name)
    with pytest.raises(KeyError, match="Unknown stage"):
        initial.get_stage("unknown")
    with pytest.raises(KeyError, match="has not run"):
        initial.get_substage("unknown")
    assert initial.complete_substage("manual").get_substage("manual").text == TEXT


def test_append_only_document_replacement_rejects_rewriting_history():
    _, second = discovered()
    citation = second.citations[0].record("name").with_case_name(TEXT, Span(0, 14))
    written = second.replace_citation(citation).complete_substage("name")
    removed = type(citation).model_validate({**citation.model_dump(mode="python"), "case_name": ()})
    with pytest.raises(ValueError, match="append-only"):
        written.replace_citation(removed)
    without_node = type(citation).model_validate(
        {**citation.model_dump(mode="python"), "nodes": citation.nodes[:1], "case_name": ()}
    )
    with pytest.raises(ValueError, match="nodes must be append-only"):
        written.replace_citation(without_node)
    with pytest.raises(ValueError, match="already exists"):
        written.add_citation(reporter())
    with pytest.raises(KeyError, match="Unknown citation"):
        written.replace_citation(reporter(identifier="unknown"))


@pytest.mark.parametrize(
    "tamper", ["missing_node", "duplicate_node", "future_node", "foreign_source", "unordered_history"]
)
def test_native_loading_rejects_invalid_field_or_node_histories(tamper):
    _, second = discovered()
    citation = second.citations[0].record("name").with_case_name(TEXT, Span(0, 14))
    final = second.replace_citation(citation).complete_substage("name")
    payload = final.model_dump(mode="json")
    item = payload["citations"][0]
    if tamper == "missing_node":
        item["case_name"][0]["node_id"] = "missing"
    elif tamper == "duplicate_node":
        item["nodes"].append(item["nodes"][-1])
    elif tamper == "future_node":
        item["nodes"].reverse()
    elif tamper == "foreign_source":
        payload["text"] = payload["text"].replace("Smith", "Smyth")
    else:
        item["case_name"].append(item["case_name"][0])
    with pytest.raises(ValidationError):
        Document.model_validate_json(json.dumps(payload))


def rooted(assignments):
    _, second = discovered()
    for citation in second.citations:
        if citation.id in assignments:
            second = second.replace_citation(citation.record("roots").with_root(assignments[citation.id]))
    return second


@pytest.mark.parametrize(
    "assignments",
    [
        {"reporter": "docket", "docket": "reporter"},
        {"reporter": "docket"},
        {"reporter": "docket", "docket": WITHDRAWN_ROOT_ID},
    ],
)
def test_invalid_root_graph_cannot_be_committed_or_loaded(assignments):
    pending = rooted(assignments)
    with pytest.raises(ValidationError, match="self-root"):
        pending.complete_substage("roots")
    payload = pending.model_dump(mode="json")
    payload["runs"].append({"kind": "substage", "name": "roots"})
    with pytest.raises(ValidationError, match="self-root"):
        Document.model_validate(payload)


def test_roots_reassignment_and_withdrawal_preserve_previous_graph():
    original = rooted({"reporter": "reporter", "docket": "reporter"}).complete_substage("roots")
    assert [item.id for item in original.roots] == ["reporter"]
    assert [item.id for item in original.leaves] == ["docket"]
    final = original.replace_citation(original.citations[1].record("withdraw").withdraw()).complete_substage(
        "withdraw"
    )
    assert final.leaves == ()
    assert final.citations[1].root_id[-1].value == WITHDRAWN_ROOT_ID
    assert final.get_substage("roots") == original
    assert Document.model_validate_json(final.model_dump_json()) == final
    with pytest.raises(ValidationError, match="unknown root"):
        original.replace_citation(original.citations[0].record("bad").with_root("absent"))


def test_later_root_creation_cannot_repair_invalid_earlier_reference():
    valid = rooted({"reporter": "reporter", "docket": "reporter"}).complete_substage("roots")
    payload = valid.model_dump(mode="json")
    payload["citations"][1]["nodes"][0]["substage"] = "roots"
    payload["citations"][0]["root_id"][0]["value"] = "docket"
    with pytest.raises(ValidationError):
        Document.model_validate(payload)


def test_colocation_commits_are_atomic_and_recoverable():
    _, second = discovered()
    pending = second.replace_citation(second.citations[0].record("colocation").with_colocation("parallel"))
    with pytest.raises(ValidationError, match="at least two"):
        pending.complete_substage("colocation")
    grouped = pending.replace_citation(
        pending.citations[1].record("colocation").with_colocation("parallel")
    ).complete_substage("colocation")
    assert grouped.colocations[0].citation_ids == ("reporter", "docket")
    assert grouped.get_substage(DOCKETS) == second


def test_toa_source_components_and_tags_survive_native_recovery():
    original = document(index_spans=(TableOfAuthoritiesComponent(0, 34),))
    first = original.add_citation(reporter()).complete_substage(REPORTERS)
    final = first.add_citation(docket()).complete_substage(DOCKETS)
    assert final.citations[0].is_toa()
    assert not final.citations[1].is_toa()
    assert Document.model_validate_json(final.model_dump_json()).get_substage(REPORTERS) == first
    payload = final.model_dump(mode="json")
    payload["citations"][0]["tags"][0]["component_index"] = 10
    with pytest.raises(ValidationError, match="component tags must match"):
        Document.model_validate(payload)
    payload["citations"][0]["tags"] = []
    with pytest.raises(ValidationError, match="component tags must match"):
        Document.model_validate_json(json.dumps(payload))


def test_model_imports_do_not_load_runtime_stages_or_provider_clients():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from mellea_lrc.model import Document; assert not any(name.startswith(('mellea_lrc.extraction', 'mellea_lrc.validation', 'mellea_lrc.providers', 'mellea_lrc.llm', 'mellea_lrc.workflows')) for name in sys.modules)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
