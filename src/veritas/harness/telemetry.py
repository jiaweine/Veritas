from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from typing import Any

from .models import HarnessEvent

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_tracer: Any | None = None
_initialized = False
_warned = False


def _enabled() -> bool:
    return os.environ.get("VERITAS_OTEL_EXPORT", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _observability_dependencies_available() -> bool:
    try:
        return (
            find_spec("opentelemetry.sdk") is not None
            and find_spec("opentelemetry.exporter.otlp.proto.http.trace_exporter") is not None
        )
    except ModuleNotFoundError:
        return False


def telemetry_capability() -> dict[str, object]:
    return {
        "enabled": _enabled(),
        "dependencies_available": _observability_dependencies_available(),
        "protocol": "otlp/http-protobuf",
        "endpoint_configured": bool(
            os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
            or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        ),
        "metadata_only": True,
        "raw_prompts_exported": False,
        "evidence_text_exported": False,
    }


def _package_version() -> str:
    try:
        return version("veritas-audit")
    except PackageNotFoundError:
        return "unknown"


def _get_tracer() -> Any | None:
    global _initialized, _tracer, _warned
    if not _enabled():
        return None
    if _initialized:
        return _tracer

    with _lock:
        if _initialized:
            return _tracer
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            if not _warned:
                _log.warning(
                    'VERITAS_OTEL_EXPORT is enabled but observability dependencies are unavailable; '
                    'install Veritas with the "observability" extra'
                )
                _warned = True
            _initialized = True
            _tracer = None
            return None

        resource = Resource.create(
            {
                "service.name": os.environ.get("VERITAS_OTEL_SERVICE_NAME", "veritas-audit"),
                "service.version": _package_version(),
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        _tracer = provider.get_tracer("veritas.harness", _package_version())
        _initialized = True
        return _tracer


def _timestamp_ns(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return int(parsed.timestamp() * 1_000_000_000)


def _parser_ids(parsers: object) -> list[str]:
    if not isinstance(parsers, list):
        return []
    values: list[str] = []
    for parser in parsers:
        if isinstance(parser, str):
            values.append(parser)
        elif isinstance(parser, dict):
            parser_id = parser.get("parser_id") or parser.get("parser") or parser.get("name")
            if parser_id:
                values.append(str(parser_id))
    return values


def export_terminal_run(record: dict[str, Any], event: HarnessEvent) -> bool:
    """Export one terminal Harness tool event as an OTLP span when explicitly enabled.

    The exporter intentionally emits metadata only. It does not include the PDF,
    evidence text, raw prompts, agent messages, or arbitrary event payloads.
    Export failures never change the local audit result.
    """

    if event.kind != "tool":
        return False
    payload = event.payload or {}
    phase = payload.get("phase")
    if phase not in {"finish", "error"}:
        return False
    tracer = _get_tracer()
    if tracer is None:
        return False

    result = payload.get("result") or {}
    counts = result.get("counts") or {}
    run_id = str(payload.get("run_id") or event.event_id)
    tool = str(payload.get("tool") or "audit.tool")
    run_kind = str(payload.get("run_kind") or "audit")
    source = result.get("source") or {}
    duration_ms = float(payload.get("duration_ms") or 0.0)
    end_ns = _timestamp_ns(event.created_at)
    start_ns = None
    if end_ns is not None and duration_ms >= 0:
        start_ns = max(0, end_ns - int(duration_ms * 1_000_000))

    attributes: dict[str, Any] = {
        "veritas.run.id": run_id,
        "veritas.audit.id": str(record.get("audit_id") or event.audit_id),
        "veritas.audit.title": str(record.get("title") or ""),
        "veritas.run.kind": run_kind,
        "veritas.tool.name": tool,
        "veritas.run.phase": str(phase),
        "veritas.run.status": str(event.status),
        "veritas.run.duration_ms": duration_ms,
        "veritas.artifact.id": str(payload.get("artifact_id") or ""),
        "veritas.evidence.linked": bool(source),
        "veritas.verification.coverage": float(result.get("verification_coverage") or 0.0),
        "veritas.checks.verified": int(counts.get("verified") or 0),
        "veritas.checks.review": int(counts.get("needs_review") or 0),
        "veritas.checks.contradictions": int(counts.get("contradictions") or 0),
    }
    parser_ids = _parser_ids(payload.get("parsers"))
    if parser_ids:
        attributes["veritas.parsers"] = parser_ids
    if payload.get("error_type"):
        attributes["error.type"] = str(payload["error_type"])
    if source.get("page") is not None:
        attributes["veritas.evidence.page"] = int(source["page"])
    if source.get("table"):
        attributes["veritas.evidence.table"] = str(source["table"])

    try:
        span = tracer.start_span(
            f"veritas.{run_kind}.{tool}",
            start_time=start_ns,
            attributes=attributes,
        )
        if phase == "error":
            from opentelemetry.trace import Status, StatusCode

            span.set_status(Status(StatusCode.ERROR, str(payload.get("error_type") or "run failed")))
        if end_ns is not None:
            span.end(end_time=end_ns)
        else:
            span.end()
        return True
    except (RuntimeError, TypeError, ValueError) as exc:
        _log.warning("Unable to export Veritas run %s via OTLP: %s", run_id, exc)
        return False
