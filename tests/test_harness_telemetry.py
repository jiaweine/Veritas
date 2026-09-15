from __future__ import annotations

from veritas.harness import telemetry
from veritas.harness.models import HarnessEvent


class _FakeSpan:
    def __init__(self) -> None:
        self.end_time = None

    def end(self, *, end_time=None) -> None:
        self.end_time = end_time


class _FakeTracer:
    def __init__(self) -> None:
        self.name = None
        self.kwargs = None
        self.span = _FakeSpan()

    def start_span(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs
        return self.span


def test_terminal_run_export_is_metadata_only(monkeypatch) -> None:
    tracer = _FakeTracer()
    monkeypatch.setattr(telemetry, "_get_tracer", lambda: tracer)
    event = HarnessEvent(
        audit_id="audit_abc123",
        kind="tool",
        title="Regression consistency checked",
        status="success",
        payload={
            "tool": "audit.regression",
            "run_kind": "detector",
            "run_id": "run_123",
            "phase": "finish",
            "duration_ms": 25.5,
            "artifact_id": "paper-abc",
            "parsers": [
                {"parser_id": "pymupdf_native", "parser_family": "mupdf_native"},
                {"parser_id": "pdfplumber_native", "parser_family": "pdfminer_native"},
            ],
            "prompt": "this must never be exported",
            "result": {
                "verification_coverage": 1.0,
                "counts": {"verified": 3, "needs_review": 0, "contradictions": 0},
                "source": {
                    "page": 2,
                    "table": "Table 2",
                    "text_quote": "sensitive evidence text must stay local",
                },
            },
        },
    )

    assert telemetry.export_terminal_run(
        {"audit_id": "audit_abc123", "title": "Paper title"},
        event,
    )
    attributes = tracer.kwargs["attributes"]
    assert tracer.name == "veritas.detector.audit.regression"
    assert attributes["veritas.run.id"] == "run_123"
    assert attributes["veritas.evidence.page"] == 2
    assert attributes["veritas.evidence.table"] == "Table 2"
    assert attributes["veritas.parsers"] == ["pymupdf_native", "pdfplumber_native"]
    rendered = repr(attributes)
    assert "this must never be exported" not in rendered
    assert "sensitive evidence text must stay local" not in rendered
    assert tracer.span.end_time is not None


def test_nonterminal_events_are_not_exported(monkeypatch) -> None:
    tracer = _FakeTracer()
    monkeypatch.setattr(telemetry, "_get_tracer", lambda: tracer)
    event = HarnessEvent(
        audit_id="audit_abc123",
        kind="tool",
        title="Regression audit",
        status="running",
        payload={"run_id": "run_123", "phase": "start"},
    )
    assert telemetry.export_terminal_run({"audit_id": "audit_abc123"}, event) is False
    assert tracer.name is None
