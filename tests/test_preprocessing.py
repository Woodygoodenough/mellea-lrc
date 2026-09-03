"""Tests for preprocessing."""

import sys
import types

import pytest

from mellea_lrc.core import SourceMetadata
from mellea_lrc.preprocessing import (
    DEFAULT_LAYOUT_RULES,
    DocumentBase,
    LayoutRule,
    PreprocessedDocument,
    PreprocessingBackend,
    PreprocessingMetadata,
    SourceFormat,
    is_docling_supported_format,
    preprocess,
    preprocess_plain_text_from_string,
    preprocess_with_docling,
    split_plain_text_file,
)


def test_split_plain_text_file_splits_recap_header() -> None:
    raw = "Case: Example\n\n--- Plain text ---\nBody text here."
    header, body = split_plain_text_file(raw)
    assert header == "Case: Example"
    assert body == "Body text here."


def test_preprocess_plain_text_from_string_wraps_text() -> None:
    document = preprocess_plain_text_from_string("Hello world.", source_path="sample.txt")
    assert document.text == "Hello world."
    assert isinstance(document, DocumentBase)
    assert document.source_metadata.path == "sample.txt"
    assert document.preprocessing_metadata.backend == PreprocessingBackend.PLAIN_TEXT
    assert document.source_metadata.format == SourceFormat.TEXT


def test_is_docling_supported_format_checks_supported_suffixes() -> None:
    assert is_docling_supported_format("sample.pdf")
    assert is_docling_supported_format("sample.docx")
    assert not is_docling_supported_format("sample.csv")


def test_preprocess_rejects_unsupported_format() -> None:
    with pytest.raises(ValueError, match=r"Unsupported document format: \.csv"):
        preprocess("sample.csv")


def test_preprocess_rejects_path_without_suffix() -> None:
    with pytest.raises(ValueError, match="Unsupported document format: <none>"):
        preprocess("sample")


def test_preprocess_with_docling_exports_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str | bool] = {}

    class FakeDocument:
        # The index locator walks these, so they have to exist. Empty here:
        # this test is about which export is called.
        tables: tuple[object, ...] = ()

        def export_to_text(self) -> str:
            calls["export_to_text"] = True
            return "Plain text"

        def export_to_markdown(self, **_kwargs: object) -> str:
            raise AssertionError("Expected Docling preprocessing to export plain text")

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, path: str) -> FakeResult:
            calls["path"] = path
            return FakeResult()

    fake_docling = types.ModuleType("docling")
    fake_converter_module = types.ModuleType("docling.document_converter")
    fake_converter_module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", fake_docling)
    monkeypatch.setitem(sys.modules, "docling.document_converter", fake_converter_module)

    # No layout rules: this test is about which export is called, and the rules
    # need a real Docling document to walk.
    document = preprocess_with_docling("sample.pdf", layout_rules=())

    assert document.text == "Plain text"
    assert document.source_metadata.format == SourceFormat.PDF
    assert document.preprocessing_metadata.backend == PreprocessingBackend.DOCLING
    assert calls == {"path": "sample.pdf", "export_to_text": True}
    assert document.index_spans == ()


def test_docling_runs_the_rules_it_was_given_and_records_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every rule in the list runs, and the result says which did.

    A rule that is exported but never reached removes nothing, and a document
    rendered without it is a different coordinate space than one rendered with
    it. The record is what tells the two apart.
    """

    class FakeDocument:
        # Both rules walk these. Empty here: this test is about which rules run.
        texts: tuple[object, ...] = ()

        def export_to_text(self) -> str:
            return "Plain text"

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, path: str) -> FakeResult:
            return FakeResult()

    fake_docling = types.ModuleType("docling")
    fake_converter_module = types.ModuleType("docling.document_converter")
    fake_converter_module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", fake_docling)
    monkeypatch.setitem(sys.modules, "docling.document_converter", fake_converter_module)

    document = preprocess_with_docling("sample.pdf")

    assert document.preprocessing_metadata.layout_rules == DEFAULT_LAYOUT_RULES
    assert document.preprocessing_metadata.layout_removals == (
        (LayoutRule.MARGIN_LINE_NUMBERS, 0),
        (LayoutRule.REPEATED_FURNITURE, 0),
    )

    kept = preprocess_with_docling("sample.pdf", layout_rules=())
    assert kept.preprocessing_metadata.layout_rules == ()
    assert kept.preprocessing_metadata.layout_removals == ()


def test_preprocessed_document_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        PreprocessedDocument(
            source_metadata=SourceMetadata(),
            text="",
            preprocessing_metadata=PreprocessingMetadata(),
        )
