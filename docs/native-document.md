# Native Document foundation

`mellea_lrc.model.Document` persists source text, typed full reporter/docket citations, and their complete field histories through Pydantic. This increment adds the data model; it does not change the existing CLI or extraction and validation pipelines.

```python
from mellea_lrc.model import (
    Document,
    FullReporterCitation,
    PreprocessedDocument,
    PreprocessingMetadata,
    SourceMetadata,
    Span,
)

text = "Smith v. Jones, 347 U.S. 483 (1954)."
document = Document.from_preprocessed(
    PreprocessedDocument(
        text=text,
        source_metadata=SourceMetadata(path="filing.txt"),
        preprocessing_metadata=PreprocessingMetadata(),
    )
)
citation = FullReporterCitation.from_locator(
    citation_id="reporter:15:27",
    substage="discover",
    source=text,
    span=Span(15, 27),
)
document = document.add_citation(citation).complete_substage("discover")
citation = citation.record("read_name").with_case_name(text, Span(0, 14))
document = document.replace_citation(citation).complete_substage("read_name")

saved = document.model_dump_json()
restored = Document.model_validate_json(saved)
assert restored == document
assert restored.get_substage("discover").citations[0].case_name == ()
```

A citation's `nodes` record decisions. Each field history entry holds its source quote, character span, typed normalization, and producing `node_id`. Named methods append readings; `Document.replace_citation()` rejects rewriting earlier nodes or field entries. Failed normalization remains a quoted reading with `normalizable=False`; its getter raises.

`complete_substage()` commits an atomic boundary, including a run with no changes. `get_substage()` restores exactly that boundary from the cumulative document. `complete_stage()` and `get_stage()` provide the same behavior for semantic groups. The initial catalog describes the planned `grow_roots` groups; it contains no execution functions. Later PRs add their own workflow definitions and histories. Unqualified names support local development checkpoints; unknown qualified names and duplicate completions raise.

Pending edits may involve multiple citations within one substage. A committed root attachment must point directly to a self-root; withdrawal appends the dummy-root assignment. Table-of-authorities tags refer to source components and remain attached to their creation node. Retrieval records, judgments, leaf kinds, and content-review records belong to later increments.
