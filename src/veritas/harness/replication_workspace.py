from __future__ import annotations

import difflib
import json
import os
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .service import AuditHarness

MAX_WORKSPACE_FILES = 5000
MAX_INSPECT_BYTES = 512 * 1024


def find_replication_audit(runtime: AuditHarness, run_id: str) -> dict[str, Any]:
    _validate_run_id(run_id)
    for audit in runtime.list_audits():
        for event in audit.get("events") or []:
            payload = event.get("payload") or {}
            if payload.get("run_id") == run_id and payload.get("run_kind") == "replication":
                return audit
    raise FileNotFoundError(f"replication run not found: {run_id}")


def replication_workspace_snapshot(runtime: AuditHarness, run_id: str) -> dict[str, Any]:
    audit = find_replication_audit(runtime, run_id)
    audit_id = str(audit["audit_id"])
    workspace = _workspace_path(runtime, audit_id, run_id)
    expected = _expected_files(runtime, audit, run_id)
    current = _scan_workspace(workspace)

    files: list[dict[str, Any]] = []
    for path, metadata in current.items():
        baseline = expected.get(path)
        if metadata.get("kind") == "symlink":
            change = "unsafe_link"
        elif baseline is None:
            change = "created"
        elif metadata.get("sha256") == baseline.get("sha256"):
            change = "original"
        else:
            change = "modified"
        files.append(
            {
                **metadata,
                "change": change,
                "baseline_sha256": baseline.get("sha256") if baseline else None,
                "immutable_input": bool(baseline and baseline.get("immutable_input")),
            }
        )

    for path, baseline in expected.items():
        if path in current:
            continue
        files.append(
            {
                "path": path,
                "size_bytes": 0,
                "sha256": None,
                "binary": baseline.get("binary", False),
                "kind": "file",
                "change": "deleted",
                "baseline_sha256": baseline.get("sha256"),
                "immutable_input": bool(baseline.get("immutable_input")),
            }
        )

    files.sort(key=lambda item: str(item["path"]))
    counts = {
        name: sum(1 for item in files if item.get("change") == name)
        for name in ("original", "created", "modified", "deleted", "unsafe_link")
    }
    immutable_drift = [
        item["path"]
        for item in files
        if item.get("immutable_input") and item.get("change") not in {"original"}
    ]
    return {
        "schema_version": 1,
        "run_id": run_id,
        "audit_id": audit_id,
        "workspace_is_security_boundary": False,
        "files": files,
        "counts": counts,
        "changed_files": [
            item["path"] for item in files if item.get("change") != "original"
        ],
        "staged_input_drift": immutable_drift,
        "staged_inputs_unchanged": not immutable_drift,
    }


def replication_workspace_file(
    runtime: AuditHarness,
    run_id: str,
    relative_path: str,
) -> dict[str, Any]:
    audit = find_replication_audit(runtime, run_id)
    audit_id = str(audit["audit_id"])
    workspace = _workspace_path(runtime, audit_id, run_id)
    clean_path = _clean_relative_path(relative_path)
    expected = _expected_files(runtime, audit, run_id)
    baseline = expected.get(clean_path)
    candidate = workspace.joinpath(*PurePosixPath(clean_path).parts)

    current_bytes: bytes | None = None
    current_sha: str | None = None
    current_size = 0
    deleted = False
    if candidate.exists() or candidate.is_symlink():
        safe = _safe_regular_file(workspace, candidate)
        current_size = safe.stat().st_size
        current_sha = _file_sha256(safe)
        current_bytes = _bounded_bytes(safe)
    elif baseline is not None:
        deleted = True
    else:
        raise FileNotFoundError(f"workspace file not found: {clean_path}")

    baseline_bytes = _baseline_bytes(baseline)
    if deleted:
        change = "deleted"
    elif baseline is None:
        change = "created"
    elif current_sha == baseline.get("sha256"):
        change = "original"
    else:
        change = "modified"

    current_text, current_binary, current_truncated = _decode_text(current_bytes, current_size)
    baseline_size = int(baseline.get("size_bytes") or 0) if baseline else 0
    baseline_text, baseline_binary, baseline_truncated = _decode_text(
        baseline_bytes,
        baseline_size,
    )
    diff = ""
    if change in {"created", "modified", "deleted"} and not current_binary and not baseline_binary:
        before = baseline_text or ""
        after = current_text or ""
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{clean_path}",
                tofile=f"b/{clean_path}",
                n=3,
            )
        )

    return {
        "run_id": run_id,
        "audit_id": audit_id,
        "path": clean_path,
        "change": change,
        "size_bytes": current_size,
        "sha256": current_sha,
        "baseline_sha256": baseline.get("sha256") if baseline else None,
        "immutable_input": bool(baseline and baseline.get("immutable_input")),
        "binary": current_binary,
        "baseline_binary": baseline_binary,
        "truncated": current_truncated,
        "baseline_truncated": baseline_truncated,
        "content": None if current_binary else current_text,
        "baseline_content": None if baseline_binary else baseline_text,
        "diff": diff,
    }


def normalize_replication_run(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if result.get("run_kind") == "replication" and result.get("error_type") == "ReplicationCancelledError":
        result["phase"] = "cancelled"
        result["status"] = "review"
    return result


def _workspace_path(runtime: AuditHarness, audit_id: str, run_id: str) -> Path:
    _validate_run_id(run_id)
    root = runtime.paper_path(audit_id).parent / "replication-workspaces"
    workspace = root / run_id
    if not workspace.is_dir():
        raise FileNotFoundError(f"replication workspace not found: {run_id}")
    resolved_root = root.resolve()
    resolved_workspace = workspace.resolve()
    try:
        resolved_workspace.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("replication workspace escaped its audit root") from exc
    return resolved_workspace


def _expected_files(
    runtime: AuditHarness,
    audit: dict[str, Any],
    run_id: str,
) -> dict[str, dict[str, Any]]:
    audit_id = str(audit["audit_id"])
    paper_path = runtime.paper_path(audit_id)
    expected: dict[str, dict[str, Any]] = {
        "paper.pdf": {
            "sha256": audit.get("artifact_sha256"),
            "size_bytes": paper_path.stat().st_size,
            "source": paper_path,
            "binary": True,
            "immutable_input": True,
        }
    }
    attachment_manifest: list[dict[str, Any]] = []
    for metadata in audit.get("attachments") or []:
        attachment_id = str(metadata["attachment_id"])
        source = runtime.store.get_attachment_path(audit_id, attachment_id)
        path = f"attachments/{attachment_id}/{source.name}"
        expected[path] = {
            "sha256": metadata.get("sha256"),
            "size_bytes": metadata.get("size_bytes"),
            "source": source,
            "binary": _looks_binary(source),
            "immutable_input": True,
        }
        attachment_manifest.append(
            {
                "attachment_id": attachment_id,
                "filename": source.name,
                "sha256": metadata.get("sha256"),
                "size_bytes": metadata.get("size_bytes"),
                "media_type": metadata.get("media_type"),
                "path": path,
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
        "attachments": attachment_manifest,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    expected["artifacts.json"] = {
        "sha256": sha256(manifest_bytes).hexdigest(),
        "size_bytes": len(manifest_bytes),
        "bytes": manifest_bytes,
        "binary": False,
        "immutable_input": True,
    }
    return expected


def _scan_workspace(workspace: Path) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    seen = 0
    for root, dirs, files in os.walk(workspace, followlinks=False):
        root_path = Path(root)
        kept_dirs: list[str] = []
        for name in dirs:
            path = root_path / name
            relative = path.relative_to(workspace).as_posix()
            if path.is_symlink():
                seen += 1
                items[relative] = {
                    "path": relative,
                    "size_bytes": 0,
                    "sha256": None,
                    "binary": False,
                    "kind": "symlink",
                }
            else:
                kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in files:
            path = root_path / name
            relative = path.relative_to(workspace).as_posix()
            seen += 1
            if seen > MAX_WORKSPACE_FILES:
                raise ValueError(f"replication workspace exceeds {MAX_WORKSPACE_FILES} inspectable entries")
            if path.is_symlink():
                items[relative] = {
                    "path": relative,
                    "size_bytes": 0,
                    "sha256": None,
                    "binary": False,
                    "kind": "symlink",
                }
                continue
            safe = _safe_regular_file(workspace, path)
            items[relative] = {
                "path": relative,
                "size_bytes": safe.stat().st_size,
                "sha256": _file_sha256(safe),
                "binary": _looks_binary(safe),
                "kind": "file",
            }
    return items


def _safe_regular_file(workspace: Path, candidate: Path) -> Path:
    if candidate.is_symlink():
        raise ValueError("workspace symlinks are not inspectable")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError("workspace file escaped its run directory") from exc
    relative = candidate.relative_to(workspace)
    cursor = workspace
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("workspace symlinks are not inspectable")
    if not resolved.is_file():
        raise ValueError("workspace path is not a regular file")
    return resolved


def _clean_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError("workspace file path is required")
    normalized = value.replace("\\", "/").strip()
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("workspace file path must stay inside the run workspace")
    return pure.as_posix()


def _bounded_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(MAX_INSPECT_BYTES + 1)


def _baseline_bytes(baseline: dict[str, Any] | None) -> bytes | None:
    if baseline is None:
        return None
    if isinstance(baseline.get("bytes"), bytes):
        return baseline["bytes"]
    source = baseline.get("source")
    if isinstance(source, Path):
        return _bounded_bytes(source)
    return None


def _decode_text(payload: bytes | None, size: int) -> tuple[str | None, bool, bool]:
    if payload is None:
        return "", False, False
    truncated = size > MAX_INSPECT_BYTES or len(payload) > MAX_INSPECT_BYTES
    visible = payload[:MAX_INSPECT_BYTES]
    if b"\x00" in visible:
        return None, True, truncated
    try:
        return visible.decode("utf-8"), False, truncated
    except UnicodeDecodeError:
        return None, True, truncated


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(8192)
    except OSError:
        return True
    if b"\x00" in sample:
        return True
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not run_id.startswith("run_") or not run_id[4:].isalnum():
        raise ValueError("invalid replication run id")
