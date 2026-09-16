from __future__ import annotations

from hashlib import sha256

import pymupdf
import pytest

from veritas.docling_native import DoclingNativeParser
from veritas.harness.parser_stack import parse_product_pdf
from veritas.pdf_native import NativePDFSnapshot


def _pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((30, 50), "Parser stack fixture")
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_product_parser_stack_defaults_to_locked_dual_baseline(monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_PDF_THIRD_PARSER", raising=False)
    snapshots = parse_product_pdf(_pdf(), artifact_id="paper-test")
    assert len(snapshots) == 2
    assert {snapshot.parser_family for snapshot in snapshots} == {
        "mupdf_native",
        "pdfminer_native",
    }


def test_product_parser_stack_rejects_unknown_optional_parser(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_PDF_THIRD_PARSER", "mystery-parser")
    with pytest.raises(ValueError, match="unsupported VERITAS_PDF_THIRD_PARSER"):
        parse_product_pdf(_pdf(), artifact_id="paper-test")


def test_product_parser_stack_can_append_independent_docling_snapshot(monkeypatch) -> None:
    payload = _pdf()
    monkeypatch.setenv("VERITAS_PDF_THIRD_PARSER", "docling")

    def fake_parse(self, pdf_bytes: bytes, *, artifact_id: str = "paper") -> NativePDFSnapshot:
        del self
        return NativePDFSnapshot(
            artifact_id=artifact_id,
            artifact_sha256=sha256(pdf_bytes).hexdigest(),
            parser_id="docling_native",
            parser_family="docling_layout",
            parser_version="test",
            pages=(),
        )

    monkeypatch.setattr(DoclingNativeParser, "parse_bytes", fake_parse)
    snapshots = parse_product_pdf(payload, artifact_id="paper-test")
    assert len(snapshots) == 3
    assert [snapshot.parser_family for snapshot in snapshots] == [
        "mupdf_native",
        "pdfminer_native",
        "docling_layout",
    ]


def test_optional_parser_must_preserve_artifact_identity(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_PDF_THIRD_PARSER", "docling")

    def fake_parse(self, pdf_bytes: bytes, *, artifact_id: str = "paper") -> NativePDFSnapshot:
        del self, pdf_bytes
        return NativePDFSnapshot(
            artifact_id=artifact_id,
            artifact_sha256="0" * 64,
            parser_id="docling_native",
            parser_family="docling_layout",
            parser_version="test",
            pages=(),
        )

    monkeypatch.setattr(DoclingNativeParser, "parse_bytes", fake_parse)
    with pytest.raises(RuntimeError, match="source artifact identity"):
        parse_product_pdf(_pdf(), artifact_id="paper-test")
