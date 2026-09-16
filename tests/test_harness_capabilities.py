from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def test_capabilities_disclose_safe_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_PDF_THIRD_PARSER", raising=False)
    monkeypatch.delenv("VERITAS_OTEL_EXPORT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)

    payload = TestClient(create_app(tmp_path)).get("/api/v1/capabilities").json()

    assert payload["parser_stack"]["baseline"] == [
        "pymupdf_native",
        "pdfplumber_native",
    ]
    assert payload["parser_stack"]["third_parser"] is None
    assert payload["parser_stack"]["third_parser_enabled"] is False
    assert payload["parser_stack"]["consensus_policy_changed"] is False

    assert payload["observability"]["enabled"] is False
    assert payload["observability"]["protocol"] == "otlp/http-protobuf"
    assert payload["observability"]["metadata_only"] is True
    assert payload["observability"]["raw_prompts_exported"] is False
    assert payload["observability"]["evidence_text_exported"] is False


def test_capabilities_report_explicit_optional_configuration(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_PDF_THIRD_PARSER", "docling")
    monkeypatch.setenv("VERITAS_OTEL_EXPORT", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")

    payload = TestClient(create_app(tmp_path)).get("/api/v1/capabilities").json()

    assert payload["parser_stack"]["third_parser"] == "docling"
    assert payload["parser_stack"]["third_parser_enabled"] is True
    assert payload["parser_stack"]["consensus_policy_changed"] is False
    assert payload["observability"]["enabled"] is True
    assert payload["observability"]["endpoint_configured"] is True
