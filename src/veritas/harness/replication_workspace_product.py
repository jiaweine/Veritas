from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .replication_workspace import (
    preview_replication_workspace_file,
    replication_workspace_snapshot,
)

if TYPE_CHECKING:
    from .service import AuditHarness

_CHANGE_BY_STATUS = {
    "staged_unchanged": "original",
    "staged_modified": "modified",
    "staged_deleted": "deleted",
    "created": "created",
    "created_symlink": "unsafe_link",
    "created_other": "unsafe_other",
}


def find_replication_audit(runtime: AuditHarness, run_id: str) -> dict[str, Any]:
    """Resolve a replication run to its owning audit without trusting client input."""

    for audit in runtime.list_audits():
        for event in audit.get("events") or []:
            if not isinstance(event, dict) or event.get("kind") != "tool":
                continue
            payload = event.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            if (
                payload.get("run_id") == run_id
                and payload.get("run_kind") == "replication"
                and payload.get("tool") == "replication.acp"
            ):
                return audit
    raise FileNotFoundError(f"replication run not found: {run_id}")


def replication_workspace_product_snapshot(
    runtime: AuditHarness,
    run_id: str,
) -> dict[str, Any]:
    """Project the bounded inspector into the three-pane product schema."""

    audit = find_replication_audit(runtime, run_id)
    audit_id = str(audit["audit_id"])
    raw = replication_workspace_snapshot(runtime.store, audit_id, run_id)
    files = [_project_file(item) for item in raw.get("files") or []]
    staged_drift = [
        str(item["path"])
        for item in files
        if item.get("immutable_input") and item.get("change") != "original"
    ]
    return {
        "schema_version": 1,
        "run_id": run_id,
        "audit_id": audit_id,
        "workspace_is_security_boundary": False,
        "integrity_scope": raw.get("integrity_scope"),
        "integrity_ok": bool(raw.get("integrity_ok")),
        "files": files,
        "counts": {
            "original": sum(item.get("change") == "original" for item in files),
            "created": sum(item.get("change") == "created" for item in files),
            "modified": sum(item.get("change") == "modified" for item in files),
            "deleted": sum(item.get("change") == "deleted" for item in files),
            "unsafe_link": sum(item.get("change") == "unsafe_link" for item in files),
            "unsafe_other": sum(item.get("change") == "unsafe_other" for item in files),
        },
        "changed_files": [
            str(item["path"])
            for item in files
            if item.get("change") != "original"
        ],
        "staged_input_drift": staged_drift,
        "staged_inputs_unchanged": not staged_drift,
        "bounded_inspection": raw.get("summary") or {},
        "note": raw.get("note"),
    }


def replication_workspace_product_file(
    runtime: AuditHarness,
    run_id: str,
    relative_path: str,
) -> dict[str, Any]:
    """Return one bounded file preview plus the inspector's integrity status."""

    audit = find_replication_audit(runtime, run_id)
    audit_id = str(audit["audit_id"])
    raw_snapshot = replication_workspace_snapshot(runtime.store, audit_id, run_id)
    metadata = next(
        (
            item
            for item in raw_snapshot.get("files") or []
            if isinstance(item, dict) and item.get("path") == relative_path
        ),
        None,
    )
    if metadata is None:
        raise FileNotFoundError(f"workspace file not found: {relative_path}")
    preview = preview_replication_workspace_file(runtime.store, audit_id, run_id, relative_path)
    projected = _project_file(metadata)
    return {
        "run_id": run_id,
        "audit_id": audit_id,
        "path": preview.get("path"),
        "change": projected.get("change"),
        "size_bytes": preview.get("size_bytes"),
        "sha256": metadata.get("sha256"),
        "immutable_input": projected.get("immutable_input", False),
        "binary": not bool(preview.get("previewable")),
        "previewable": bool(preview.get("previewable")),
        "truncated": bool(preview.get("truncated")),
        "encoding": preview.get("encoding"),
        "content": preview.get("content"),
        "reason": preview.get("reason"),
        "diff": "",
    }


def normalize_replication_event(
    value: dict[str, Any],
    *,
    historical_permissions: bool = False,
) -> dict[str, Any]:
    """Project one persisted/live event into product-safe replication semantics."""

    projected = dict(value)
    payload = projected.get("payload")
    if not isinstance(payload, dict):
        return projected

    outer = dict(payload)
    if (
        projected.get("kind") == "tool"
        and outer.get("error_type") == "ReplicationCancelledError"
    ):
        projected["title"] = "Replication run cancelled"
        projected["detail"] = "Cancelled by the user; the agent turn was terminated."
        projected["status"] = "review"
        outer["phase"] = "cancelled"
        outer["error_type"] = None
        terminal_result = outer.get("result")
        if isinstance(terminal_result, dict):
            normalized_terminal_result = dict(terminal_result)
            normalized_terminal_result["status"] = "cancelled"
            outer["result"] = normalized_terminal_result

    agent_event = outer.get("agent_event")
    if (
        historical_permissions
        and isinstance(agent_event, dict)
        and agent_event.get("kind") == "permission"
    ):
        agent_copy = dict(agent_event)
        agent_payload = agent_copy.get("payload")
        if isinstance(agent_payload, dict) and agent_payload.get("decision") == "pending":
            permission_copy = dict(agent_payload)
            permission_copy["decision"] = "historical_pending"
            agent_copy["payload"] = permission_copy
            agent_copy["detail"] = "Historical permission request; this run is no longer actionable."
            agent_copy["status"] = "review"
            outer["agent_event"] = agent_copy

    projected["payload"] = outer
    return projected


def normalize_replication_run(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize persisted replication terminal state and archived approvals."""

    result = dict(value)
    cancelled = (
        result.get("run_kind") == "replication"
        and result.get("error_type") == "ReplicationCancelledError"
    )
    if cancelled:
        result["phase"] = "cancelled"
        result["status"] = "review"
        result["task"] = "Replication run cancelled"
        result["error_type"] = None

    events = result.get("events")
    if isinstance(events, list):
        result["events"] = [
            normalize_replication_event(event, historical_permissions=True)
            if isinstance(event, dict)
            else event
            for event in events
        ]
    return result


def _project_file(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status") or "")
    kind = str(item.get("kind") or "file")
    change = _CHANGE_BY_STATUS.get(status, status or "unknown")
    if kind == "symlink":
        change = "unsafe_link"
    elif kind == "other" and change != "deleted":
        change = "unsafe_other"
    staged_role = item.get("staged_role")
    return {
        "path": item.get("path"),
        "size_bytes": item.get("size_bytes") or 0,
        "sha256": item.get("sha256"),
        "hash_computed": bool(item.get("hash_computed")),
        "kind": kind,
        "change": change,
        "immutable_input": staged_role is not None,
        "staged_role": staged_role,
        "exists": bool(item.get("exists")),
    }
