"""Tests for preprocessing."""

import sys
import types

import pytest

from mellea_lrc.core import SourceMetadata
from mellea_lrc.preprocessing import (
    DocumentBase,
    PreprocessedDocument,
    PreprocessingBackend,
    PreprocessingMetadata,
    SourceFormat,
    is_docling_supported_format,
    preprocess,
    preprocess_plain_text_from_string,
    looks_like_a_stamp,
    preprocess_with_docling,
)


def test_a_text_file_is_its_text() -> None:
    """Nothing is stripped from the front, so a file offset is a document offset."""
    raw = "Case: Example\n\n--- Plain text ---\nBody text here."
    document = preprocess_plain_text_from_string(raw)
    assert document.text == raw


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


def test_preprocessed_document_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        PreprocessedDocument(
            source_metadata=SourceMetadata(),
            text="",
            preprocessing_metadata=PreprocessingMetadata(),
        )


def test_a_filing_stamp_is_recognised_whatever_court_printed_it() -> None:
    """The gate is loose on purpose: no one court's wording is required."""
    assert looks_like_a_stamp("Case 2:25-cv-01295-GMS     Document 1     Filed 04/18/25     Page 6 of 32")
    assert looks_like_a_stamp(
        "Case No. 1:24-cv-00814-PAB-SBP   Document 77   filed 10/27/25   USDC Colorado   pg 1 of 9"
    )
    assert looks_like_a_stamp("Case: 1:24-cv-00074-SA-DAS Doc #: 79-1 Filed: 12/19/25 1 of 3 PageID #: 513")


def test_prose_is_not_a_filing_stamp() -> None:
    """A sentence that mentions a case and a page is still a sentence."""
    assert not looks_like_a_stamp("In that case the court reached page 12 of the opinion before saying so.")
    assert not looks_like_a_stamp("See Ashcroft v. Iqbal, 556 U.S. 662, 678 (2009).")
    assert not looks_like_a_stamp("")
