from __future__ import annotations

from typing import Any


def project_run_detail(
    audits: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any] | None:
    """Project one correlated run from persisted Harness events.

    The store remains append-only at the event level. This view groups events by
    the shared ``payload.run_id`` introduced by the product trace contract. For
    older terminal tool events that predate correlated run ids, the event id is
    accepted as a compatibility fallback.
    """

    for audit in audits:
        matched: list[dict[str, Any]] = []
        for event in audit.get("events") or []:
            payload = event.get("payload") or {}
            event_run_id = payload.get("run_id")
            if event_run_id == run_id or (not event_run_id and event.get("event_id") == run_id):
                matched.append(event)

        if not matched:
            continue

        terminal = next(
            (
                event
                for event in reversed(matched)
                if (event.get("payload") or {}).get("phase") in {"finish", "error"}
            ),
            matched[-1],
        )
        terminal_payload = terminal.get("payload") or {}
        result = terminal_payload.get("result") or {}
        source = result.get("source") or {}
        start = next(
            (
                event
                for event in matched
                if (event.get("payload") or {}).get("phase") == "start"
            ),
            matched[0],
        )
        start_payload = start.get("payload") or {}

        return {
            "run_id": run_id,
            "audit_id": audit.get("audit_id"),
            "audit_title": audit.get("title"),
            "artifact_sha256": audit.get("artifact_sha256"),
            "tool": terminal_payload.get("tool") or start_payload.get("tool") or "audit.tool",
            "run_kind": terminal_payload.get("run_kind")
            or start_payload.get("run_kind")
            or "audit",
            "status": terminal.get("status"),
            "phase": terminal_payload.get("phase") or "finish",
            "duration_ms": terminal_payload.get("duration_ms"),
            "artifact_id": terminal_payload.get("artifact_id")
            or start_payload.get("artifact_id"),
            "parsers": terminal_payload.get("parsers") or start_payload.get("parsers") or [],
            "error_type": terminal_payload.get("error_type"),
            "evidence": bool(source),
            "source": source,
            "coverage": float(result.get("verification_coverage") or 0.0),
            "counts": result.get("counts") or {},
            "started_at": start.get("created_at"),
            "finished_at": terminal.get("created_at"),
            "events": matched,
        }

    return None
