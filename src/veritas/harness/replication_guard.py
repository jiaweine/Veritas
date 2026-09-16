from __future__ import annotations

from collections.abc import AsyncIterator
from hashlib import sha256
from time import perf_counter
from typing import Any
from uuid import uuid4

from .models import HarnessEvent
from .service import AuditHarness


def _persist_failure(
    runtime: AuditHarness,
    audit_id: str,
    prompt: str,
    exc: OSError | RuntimeError | TypeError | ValueError,
    *,
    started: float,
    run_id: str | None,
    stage: str,
) -> list[dict[str, Any]]:
    record = runtime.get_audit(audit_id)
    capability = runtime.replication_capability()
    artifact_id = str((record.get("paper_summary") or {}).get("artifact_id") or "")
    attachments = list(record.get("attachments") or [])
    clean_prompt = prompt.strip()
    events: list[dict[str, Any]] = []

    if run_id is None:
        run_id = f"run_{uuid4().hex[:12]}"
        start = HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Replication agent run",
            detail="Preparing a run-specific audit workspace.",
            status="running",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "start",
                "stage": "workspace_prepare",
                "artifact_id": artifact_id,
                "attachment_count": len(attachments),
                "agent": capability.get("agent"),
                "permission_policy": capability.get("permission_policy") or "deny",
                "prompt_sha256": sha256(clean_prompt.encode("utf-8")).hexdigest(),
                "prompt_chars": len(clean_prompt),
                "workspace_is_security_boundary": False,
            },
        )
        runtime.store.append_event(start)
        events.append(start.to_dict())

    failed = HarnessEvent(
        audit_id=audit_id,
        kind="tool",
        title="Replication run failed",
        detail=f"{type(exc).__name__}: {exc}",
        status="danger",
        payload={
            "tool": "replication.acp",
            "run_kind": "replication",
            "run_id": run_id,
            "phase": "error",
            "stage": stage,
            "duration_ms": round((perf_counter() - started) * 1000, 3),
            "artifact_id": artifact_id,
            "attachment_count": len(attachments),
            "agent": capability.get("agent"),
            "permission_policy": capability.get("permission_policy") or "deny",
            "error_type": type(exc).__name__,
            "result": {
                "status": "error",
                "verification_coverage": 0.0,
                "counts": {},
            },
        },
    )
    runtime.store.append_event(failed)
    events.append(failed.to_dict())
    return events


async def stream_replication_guarded(
    runtime: AuditHarness,
    audit_id: str,
    prompt: str,
) -> AsyncIterator[dict[str, Any]]:
    """Keep replication failures inside the persisted run lifecycle.

    Immutable paper and attachment hashes are preflighted before the harness is
    allowed to create a run workspace. AuditHarness remains authoritative for
    the normal start/update/finish/error lifecycle; this guard only fills errors
    that would otherwise escape before or outside that lifecycle.
    """

    started = perf_counter()
    run_id: str | None = None
    emitted = False

    try:
        record = runtime.get_audit(audit_id)
        runtime.store.get_pdf_path(audit_id)
        for metadata in record.get("attachments") or []:
            runtime.store.get_attachment_path(
                audit_id,
                str(metadata.get("attachment_id") or ""),
            )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        for event in _persist_failure(
            runtime,
            audit_id,
            prompt,
            exc,
            started=started,
            run_id=None,
            stage="workspace_prepare",
        ):
            yield event
        return

    try:
        async for event in runtime.stream_replication(audit_id, prompt):
            emitted = True
            payload = event.get("payload") or {}
            candidate = payload.get("run_id")
            if candidate:
                run_id = str(candidate)
            yield event
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        for event in _persist_failure(
            runtime,
            audit_id,
            prompt,
            exc,
            started=started,
            run_id=run_id,
            stage="stream" if emitted else "workspace_prepare",
        ):
            yield event
