from __future__ import annotations

import json
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path
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
_MAX_DIFF_INPUT_BYTES = 256 * 1024
_MAX_DIFF_OUTPUT_BYTES = 512 * 1024


def find_replication_audit(runtime: AuditHarness, run_id: str) -> dict[str, Any]:
    """Resolve a replication run to its owning audit without trusting client input."""

    runtime_projector = getattr(runtime, "run_detail", None)
    metadata_projector = getattr(runtime, "get_audit_metadata", None)
    if callable(runtime_projector) and callable(metadata_projector):
        detail = runtime_projector(run_id)
        if (
            isinstance(detail, dict)
            and detail.get("run_kind") == "replication"
            and detail.get("tool") == "replication.acp"
        ):
            audit_id = str(detail.get("audit_id") or "")
            if audit_id:
                return metadata_projector(audit_id)
        raise FileNotFoundError(f"replication run not found: {run_id}")

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
    """Return one bounded file preview plus a bounded text diff when possible.

    Existing workspace files are still validated by the authoritative preview
    inspector, preserving traversal and symlink rejection semantics. A deleted
    immutable staged file is the one exception: after the preview reports it
    missing, the trusted snapshot may authorize a baseline-only deletion diff.
    """

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

    try:
        preview = preview_replication_workspace_file(
            runtime.store,
            audit_id,
            run_id,
            relative_path,
        )
    except FileNotFoundError:
        if not isinstance(metadata, dict) or metadata.get("status") != "staged_deleted":
            raise
        preview = {
            "path": relative_path,
            "size_bytes": 0,
            "previewable": False,
            "truncated": False,
            "encoding": None,
            "content": None,
            "reason": "workspace_file_deleted",
        }

    normalized_path = str(preview.get("path") or relative_path)
    if metadata is None or metadata.get("path") != normalized_path:
        metadata = next(
            (
                item
                for item in raw_snapshot.get("files") or []
                if isinstance(item, dict) and item.get("path") == normalized_path
            ),
            None,
        )
    if metadata is None:
        raise FileNotFoundError(f"workspace file not found: {normalized_path}")

    projected = _project_file(metadata)
    diff, diff_available, diff_reason, diff_baseline = _workspace_text_diff(
        runtime,
        audit,
        run_id,
        normalized_path,
        projected,
        preview,
    )
    return {
        "run_id": run_id,
        "audit_id": audit_id,
        "path": normalized_path,
        "change": projected.get("change"),
        "size_bytes": preview.get("size_bytes"),
        "sha256": metadata.get("sha256"),
        "immutable_input": projected.get("immutable_input", False),
        "binary": _preview_is_binary(preview),
        "previewable": bool(preview.get("previewable")),
        "truncated": bool(preview.get("truncated")),
        "encoding": preview.get("encoding"),
        "content": preview.get("content"),
        "reason": preview.get("reason"),
        "diff": diff,
        "diff_available": diff_available,
        "diff_reason": diff_reason,
        "diff_baseline": diff_baseline,
        "diff_input_limit_bytes": _MAX_DIFF_INPUT_BYTES,
        "diff_output_limit_bytes": _MAX_DIFF_OUTPUT_BYTES,
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


def _workspace_text_diff(
    runtime: AuditHarness,
    audit: dict[str, Any],
    run_id: str,
    relative_path: str,
    projected: dict[str, Any],
    preview: dict[str, Any],
) -> tuple[str, bool, str | None, str | None]:
    change = str(projected.get("change") or "")
    if change == "original":
        return "", False, "unchanged", None
    if change not in {"created", "modified", "deleted"}:
        return "", False, "unsupported_change_type", None

    if change == "created":
        baseline_text = ""
        baseline_label = "empty"
    else:
        baseline_bytes, baseline_reason = _immutable_baseline_bytes(
            runtime,
            audit,
            run_id,
            relative_path,
        )
        baseline_label = "immutable_source"
        if baseline_bytes is None:
            return "", False, baseline_reason or "baseline_unavailable", baseline_label
        baseline_text, baseline_reason = _decode_diff_text(baseline_bytes, side="baseline")
        if baseline_text is None:
            return "", False, baseline_reason, baseline_label

    if change == "deleted":
        current_text = ""
    else:
        if bool(preview.get("truncated")):
            return "", False, "current_too_large", baseline_label
        if not bool(preview.get("previewable")):
            reason = str(preview.get("reason") or "current_not_text")
            if reason == "binary_content":
                reason = "current_binary"
            elif reason == "non_utf8_content":
                reason = "current_non_utf8"
            return "", False, reason, baseline_label
        current_text = str(preview.get("content") or "")

    fromfile = "/dev/null" if change == "created" else f"a/{relative_path}"
    tofile = "/dev/null" if change == "deleted" else f"b/{relative_path}"
    rendered = "".join(
        unified_diff(
            baseline_text.splitlines(keepends=True),
            current_text.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
            lineterm="\n",
        )
    )
    if not rendered and change in {"created", "deleted"}:
        rendered = f"--- {fromfile}\n+++ {tofile}\n"
    if len(rendered.encode("utf-8")) > _MAX_DIFF_OUTPUT_BYTES:
        return "", False, "diff_too_large", baseline_label
    return rendered, True, None, baseline_label


def _immutable_baseline_bytes(
    runtime: AuditHarness,
    audit: dict[str, Any],
    run_id: str,
    relative_path: str,
) -> tuple[bytes | None, str | None]:
    audit_id = str(audit["audit_id"])
    if relative_path == "paper.pdf":
        return None, "baseline_binary"
    if relative_path == "artifacts.json":
        payload = _expected_manifest_bytes(audit, run_id)
        if len(payload) > _MAX_DIFF_INPUT_BYTES:
            return None, "baseline_too_large"
        return payload, None

    for metadata in audit.get("attachments") or []:
        if not isinstance(metadata, dict):
            continue
        attachment_id = str(metadata.get("attachment_id") or "")
        filename = str(metadata.get("filename") or "")
        if not attachment_id or not filename:
            continue
        expected_path = f"attachments/{attachment_id}/{filename}"
        if expected_path != relative_path:
            continue
        source = runtime.store.get_attachment_path(audit_id, attachment_id)
        payload, too_large = _read_bounded(source)
        if too_large:
            return None, "baseline_too_large"
        expected_hash = str(metadata.get("sha256") or "")
        if expected_hash and sha256(payload).hexdigest() != expected_hash:
            raise ValueError(f"immutable attachment changed while preparing diff: {attachment_id}")
        return payload, None
    return None, "baseline_unavailable"


def _read_bounded(path: Path) -> tuple[bytes, bool]:
    with path.open("rb") as handle:
        payload = handle.read(_MAX_DIFF_INPUT_BYTES + 1)
    if len(payload) > _MAX_DIFF_INPUT_BYTES:
        return payload[:_MAX_DIFF_INPUT_BYTES], True
    return payload, False


def _decode_diff_text(payload: bytes, *, side: str) -> tuple[str | None, str | None]:
    if b"\x00" in payload:
        return None, f"{side}_binary"
    try:
        return payload.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, f"{side}_non_utf8"


def _expected_manifest_bytes(audit: dict[str, Any], run_id: str) -> bytes:
    attachments = []
    for metadata in audit.get("attachments") or []:
        if not isinstance(metadata, dict):
            continue
        attachment_id = str(metadata.get("attachment_id") or "")
        filename = str(metadata.get("filename") or "")
        if not attachment_id or not filename:
            continue
        attachments.append(
            {
                "attachment_id": attachment_id,
                "filename": filename,
                "sha256": metadata.get("sha256"),
                "size_bytes": metadata.get("size_bytes"),
                "media_type": metadata.get("media_type"),
                "path": f"attachments/{attachment_id}/{filename}",
            }
        )
    manifest = {
        "schema_version": "1",
        "run_id": run_id,
        "paper": {
            "filename": "paper.pdf",
            "sha256": audit.get("artifact_sha256"),
            "artifact_id": (audit.get("paper_summary") or {}).get("artifact_id"),
        },
        "attachments": attachments,
    }
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _preview_is_binary(preview: dict[str, Any]) -> bool:
    return preview.get("reason") in {"binary_content", "non_utf8_content"}
