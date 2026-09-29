from __future__ import annotations

import codecs
import json
import os
import re
import stat
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from .store import HarnessStore

_RUN_ID_RE = re.compile(r"^run_[0-9a-f]{12}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ENTRIES = 1000
_MAX_STAGED_FILE_BYTES = 96 * 1024 * 1024
_MAX_CREATED_HASH_BYTES = 8 * 1024 * 1024
_MAX_CREATED_HASH_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_PREVIEW_BYTES = 256 * 1024
_HASH_CHUNK_BYTES = 1024 * 1024


def replication_workspace_snapshot(
    store: HarnessStore,
    audit_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Inspect one persisted replication workspace without following symlinks.

    The returned integrity state is deliberately narrow: it says whether the
    read-only paper/attachment/manifest copies staged by Veritas still match
    their audit-record identities. It does not claim that generated outputs are
    correct, trustworthy, sandboxed, or reproducible.
    """

    record = store.get_audit(audit_id)
    workspace = _authorized_workspace(store, audit_id, record, run_id)
    expected = _expected_staged_objects(record, run_id)

    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    entries_scanned = 0
    directories = 0
    created_hash_bytes = 0

    def walk(directory: Path, prefix: str = "") -> None:
        nonlocal entries_scanned, directories, created_hash_bytes
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise RuntimeError(f"unable to inspect replication workspace: {exc}") from exc

        for entry in entries:
            entries_scanned += 1
            if entries_scanned > _MAX_ENTRIES:
                raise RuntimeError(
                    f"replication workspace exceeds the {_MAX_ENTRIES}-entry inspection limit"
                )
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            staged = expected.get(relative)

            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise RuntimeError(f"unable to stat replication workspace entry: {relative}") from exc

            if stat.S_ISLNK(entry_stat.st_mode):
                seen.add(relative)
                files.append(
                    {
                        "path": relative,
                        "kind": "symlink",
                        "status": "staged_modified" if staged is not None else "created_symlink",
                        "exists": True,
                        "size_bytes": entry_stat.st_size,
                        "sha256": None,
                        "hash_computed": False,
                        "staged_role": staged.get("role") if staged else None,
                    }
                )
                continue

            if stat.S_ISDIR(entry_stat.st_mode):
                directories += 1
                walk(Path(entry.path), relative)
                continue

            seen.add(relative)
            if not stat.S_ISREG(entry_stat.st_mode):
                files.append(
                    {
                        "path": relative,
                        "kind": "other",
                        "status": "staged_modified" if staged is not None else "created_other",
                        "exists": True,
                        "size_bytes": entry_stat.st_size,
                        "sha256": None,
                        "hash_computed": False,
                        "staged_role": staged.get("role") if staged else None,
                    }
                )
                continue

            size_bytes = entry_stat.st_size
            digest: str | None = None
            hash_computed = False
            status: str

            if staged is not None:
                expected_size = staged.get("size_bytes")
                size_matches = expected_size is None or size_bytes == expected_size
                if size_bytes <= _MAX_STAGED_FILE_BYTES:
                    digest = _file_sha256(Path(entry.path))
                    hash_computed = True
                status = (
                    "staged_unchanged"
                    if size_matches and digest == staged["sha256"]
                    else "staged_modified"
                )
            else:
                if (
                    size_bytes <= _MAX_CREATED_HASH_BYTES
                    and created_hash_bytes + size_bytes <= _MAX_CREATED_HASH_TOTAL_BYTES
                ):
                    digest = _file_sha256(Path(entry.path))
                    hash_computed = True
                    created_hash_bytes += size_bytes
                status = "created"

            files.append(
                {
                    "path": relative,
                    "kind": "file",
                    "status": status,
                    "exists": True,
                    "size_bytes": size_bytes,
                    "sha256": digest,
                    "hash_computed": hash_computed,
                    "staged_role": staged.get("role") if staged else None,
                }
            )

    walk(workspace)

    for relative, staged in expected.items():
        if relative in seen:
            continue
        files.append(
            {
                "path": relative,
                "kind": "file",
                "status": "staged_deleted",
                "exists": False,
                "size_bytes": None,
                "sha256": None,
                "hash_computed": False,
                "staged_role": staged["role"],
            }
        )

    files.sort(key=lambda item: str(item["path"]))
    staged_unchanged = sum(item["status"] == "staged_unchanged" for item in files)
    staged_modified = sum(item["status"] == "staged_modified" for item in files)
    staged_deleted = sum(item["status"] == "staged_deleted" for item in files)
    created = sum(item["status"] == "created" for item in files)
    symlinks = sum(item["kind"] == "symlink" for item in files)
    hash_omitted = sum(
        item["kind"] == "file" and item["exists"] and not item["hash_computed"]
        for item in files
    )

    return {
        "schema_version": "1",
        "audit_id": audit_id,
        "run_id": run_id,
        "workspace_is_security_boundary": False,
        "integrity_scope": "veritas_staged_inputs_only",
        "integrity_ok": staged_modified == 0 and staged_deleted == 0,
        "summary": {
            "entries_scanned": entries_scanned,
            "directories": directories,
            "files_present": sum(item["kind"] == "file" and item["exists"] for item in files),
            "created_files": created,
            "staged_unchanged": staged_unchanged,
            "staged_modified": staged_modified,
            "staged_deleted": staged_deleted,
            "symlinks": symlinks,
            "hash_omitted": hash_omitted,
        },
        "files": files,
        "note": (
            "Integrity covers only Veritas-staged paper, attachments, and artifacts.json. "
            "Generated files remain untrusted reproduction outputs until separately reviewed."
        ),
    }


def preview_replication_workspace_file(
    store: HarnessStore,
    audit_id: str,
    run_id: str,
    relative_path: str,
) -> dict[str, Any]:
    """Return a bounded UTF-8 preview for one run-owned regular file."""

    record = store.get_audit(audit_id)
    workspace = _authorized_workspace(store, audit_id, record, run_id)
    parts = _safe_relative_parts(relative_path)

    cursor = workspace
    final_stat: os.stat_result | None = None
    for index, part in enumerate(parts):
        cursor = cursor / part
        try:
            current_stat = os.lstat(cursor)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"workspace file not found: {relative_path}") from exc
        except OSError as exc:
            raise RuntimeError(f"unable to inspect workspace path: {relative_path}") from exc

        if stat.S_ISLNK(current_stat.st_mode):
            raise ValueError("symlink paths cannot be previewed")
        if index < len(parts) - 1 and not stat.S_ISDIR(current_stat.st_mode):
            raise FileNotFoundError(f"workspace file not found: {relative_path}")
        final_stat = current_stat

    if final_stat is None or not stat.S_ISREG(final_stat.st_mode):
        raise ValueError("workspace preview requires a regular file")

    resolved_workspace = workspace.resolve(strict=True)
    resolved_file = cursor.resolve(strict=True)
    if not resolved_file.is_relative_to(resolved_workspace):
        raise ValueError("workspace path escapes the replication run")

    try:
        with resolved_file.open("rb") as handle:
            sample = handle.read(_MAX_PREVIEW_BYTES)
    except OSError as exc:
        raise RuntimeError(f"unable to read workspace file: {relative_path}") from exc

    truncated = final_stat.st_size > len(sample)
    if b"\x00" in sample:
        return {
            "audit_id": audit_id,
            "run_id": run_id,
            "path": PurePosixPath(*parts).as_posix(),
            "size_bytes": final_stat.st_size,
            "previewable": False,
            "truncated": truncated,
            "encoding": None,
            "content": None,
            "reason": "binary_content",
        }

    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        text = decoder.decode(sample, final=not truncated)
    except UnicodeDecodeError:
        return {
            "audit_id": audit_id,
            "run_id": run_id,
            "path": PurePosixPath(*parts).as_posix(),
            "size_bytes": final_stat.st_size,
            "previewable": False,
            "truncated": truncated,
            "encoding": None,
            "content": None,
            "reason": "non_utf8_content",
        }

    return {
        "audit_id": audit_id,
        "run_id": run_id,
        "path": PurePosixPath(*parts).as_posix(),
        "size_bytes": final_stat.st_size,
        "previewable": True,
        "truncated": truncated,
        "encoding": "utf-8",
        "content": text,
        "reason": None,
    }


def _authorized_workspace(
    store: HarnessStore,
    audit_id: str,
    record: dict[str, Any],
    run_id: str,
) -> Path:
    _validate_run_id(run_id)
    if record.get("audit_id") != audit_id:
        raise FileNotFoundError(f"audit not found: {audit_id}")
    if not _audit_has_replication_run(record, run_id):
        raise FileNotFoundError(f"replication run not found for audit: {run_id}")

    audit_dir = store.root / audit_id
    workspace = audit_dir / "replication-workspaces" / run_id
    try:
        workspace_stat = os.lstat(workspace)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"replication workspace not found: {run_id}") from exc
    except OSError as exc:
        raise RuntimeError(f"unable to inspect replication workspace: {run_id}") from exc
    if stat.S_ISLNK(workspace_stat.st_mode) or not stat.S_ISDIR(workspace_stat.st_mode):
        raise ValueError("replication workspace root must be a real directory")

    resolved_audit = audit_dir.resolve(strict=True)
    resolved_workspace = workspace.resolve(strict=True)
    if not resolved_workspace.is_relative_to(resolved_audit):
        raise ValueError("replication workspace escapes the audit directory")
    return workspace


def _audit_has_replication_run(record: dict[str, Any], run_id: str) -> bool:
    for event in record.get("events") or []:
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
            return True
    return False


def _expected_staged_objects(record: dict[str, Any], run_id: str) -> dict[str, dict[str, Any]]:
    paper_sha = _require_sha256(record.get("artifact_sha256"), "paper sha256")
    expected: dict[str, dict[str, Any]] = {
        "paper.pdf": {
            "sha256": paper_sha,
            "size_bytes": None,
            "role": "paper",
        }
    }

    attachment_manifest: list[dict[str, Any]] = []
    for metadata in record.get("attachments") or []:
        if not isinstance(metadata, dict):
            raise ValueError("audit attachment metadata is invalid")
        attachment_id = str(metadata.get("attachment_id") or "")
        if not attachment_id.startswith("att_") or not attachment_id[4:].isalnum():
            raise ValueError("audit attachment id is invalid")
        filename = str(metadata.get("filename") or "")
        if (
            not filename
            or filename in {".", ".."}
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
        ):
            raise ValueError("audit attachment filename is invalid")
        digest = _require_sha256(metadata.get("sha256"), "attachment sha256")
        size_bytes = metadata.get("size_bytes")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise ValueError("audit attachment size is invalid")
        relative = f"attachments/{attachment_id}/{filename}"
        expected[relative] = {
            "sha256": digest,
            "size_bytes": size_bytes,
            "role": "attachment",
        }
        attachment_manifest.append(
            {
                "attachment_id": attachment_id,
                "filename": filename,
                "sha256": digest,
                "size_bytes": size_bytes,
                "media_type": metadata.get("media_type"),
                "path": relative,
            }
        )

    manifest = {
        "schema_version": "1",
        "run_id": run_id,
        "paper": {
            "filename": "paper.pdf",
            "sha256": paper_sha,
            "artifact_id": (record.get("paper_summary") or {}).get("artifact_id"),
        },
        "attachments": attachment_manifest,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    expected["artifacts.json"] = {
        "sha256": sha256(manifest_bytes).hexdigest(),
        "size_bytes": len(manifest_bytes),
        "role": "manifest",
    }
    return expected


def _safe_relative_parts(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str):
        raise ValueError("workspace path must be text")
    if not relative_path or len(relative_path) > 512 or "\x00" in relative_path:
        raise ValueError("workspace path is invalid")
    if "\\" in relative_path:
        raise ValueError("workspace path must use POSIX separators")
    raw_parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("workspace path must be a normalized relative path")
    pure = PurePosixPath(relative_path)
    if pure.is_absolute():
        raise ValueError("workspace path must be relative")
    return tuple(raw_parts)


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError("invalid replication run id")


def _require_sha256(value: object, label: str) -> str:
    text = str(value or "")
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{label} is invalid")
    return text


def _file_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RuntimeError(f"unable to hash workspace file: {path.name}") from exc
    return digest.hexdigest()
