from __future__ import annotations

import codecs
import errno
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
_SECURE_DESCRIPTOR_TRAVERSAL = (
    os.open in getattr(os, "supports_dir_fd", set())
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_FLAGS = _READ_FLAGS | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = _READ_FLAGS | getattr(os, "O_NOFOLLOW", 0)


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

    def record_entry(
        *,
        relative: str,
        entry_stat: os.stat_result,
        staged: dict[str, Any] | None,
        digest: str | None,
        hash_computed: bool,
        status: str,
        kind: str = "file",
    ) -> None:
        files.append(
            {
                "path": relative,
                "kind": kind,
                "status": status,
                "exists": True,
                "size_bytes": entry_stat.st_size,
                "sha256": digest,
                "hash_computed": hash_computed,
                "staged_role": staged.get("role") if staged else None,
            }
        )

    def handle_regular(
        relative: str,
        staged: dict[str, Any] | None,
        entry_stat: os.stat_result,
        *,
        file_fd: int | None,
        path: Path | None,
    ) -> None:
        nonlocal created_hash_bytes
        size_bytes = entry_stat.st_size
        digest: str | None = None
        hash_computed = False

        if staged is not None:
            expected_size = staged.get("size_bytes")
            size_matches = expected_size is None or size_bytes == expected_size
            if size_bytes <= _MAX_STAGED_FILE_BYTES:
                digest = _file_sha256_fd(file_fd) if file_fd is not None else _file_sha256(path)
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
                digest = _file_sha256_fd(file_fd) if file_fd is not None else _file_sha256(path)
                hash_computed = True
                created_hash_bytes += size_bytes
            status = "created"

        record_entry(
            relative=relative,
            entry_stat=entry_stat,
            staged=staged,
            digest=digest,
            hash_computed=hash_computed,
            status=status,
        )

    def walk_fd(directory_fd: int, prefix: str = "") -> None:
        nonlocal entries_scanned, directories
        try:
            with os.scandir(directory_fd) as scan:
                entries = sorted(scan, key=lambda item: item.name)
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
                record_entry(
                    relative=relative,
                    entry_stat=entry_stat,
                    staged=staged,
                    digest=None,
                    hash_computed=False,
                    status="staged_modified" if staged is not None else "created_symlink",
                    kind="symlink",
                )
                continue

            if stat.S_ISDIR(entry_stat.st_mode):
                directories += 1
                child_fd = _open_directory_at(entry.name, directory_fd, relative)
                try:
                    child_stat = os.fstat(child_fd)
                    _require_same_entry(entry_stat, child_stat, relative)
                    walk_fd(child_fd, relative)
                finally:
                    os.close(child_fd)
                continue

            seen.add(relative)
            if not stat.S_ISREG(entry_stat.st_mode):
                record_entry(
                    relative=relative,
                    entry_stat=entry_stat,
                    staged=staged,
                    digest=None,
                    hash_computed=False,
                    status="staged_modified" if staged is not None else "created_other",
                    kind="other",
                )
                continue

            file_fd = _open_file_at(entry.name, directory_fd, relative)
            try:
                file_stat = os.fstat(file_fd)
                _require_same_entry(entry_stat, file_stat, relative)
                if not stat.S_ISREG(file_stat.st_mode):
                    raise RuntimeError(f"workspace entry changed type during inspection: {relative}")
                handle_regular(relative, staged, file_stat, file_fd=file_fd, path=None)
            finally:
                os.close(file_fd)

    def walk_path(directory: Path, prefix: str = "") -> None:
        nonlocal entries_scanned, directories
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
                record_entry(
                    relative=relative,
                    entry_stat=entry_stat,
                    staged=staged,
                    digest=None,
                    hash_computed=False,
                    status="staged_modified" if staged is not None else "created_symlink",
                    kind="symlink",
                )
                continue
            if stat.S_ISDIR(entry_stat.st_mode):
                directories += 1
                walk_path(Path(entry.path), relative)
                continue
            seen.add(relative)
            if not stat.S_ISREG(entry_stat.st_mode):
                record_entry(
                    relative=relative,
                    entry_stat=entry_stat,
                    staged=staged,
                    digest=None,
                    hash_computed=False,
                    status="staged_modified" if staged is not None else "created_other",
                    kind="other",
                )
                continue
            handle_regular(relative, staged, entry_stat, file_fd=None, path=Path(entry.path))

    if _SECURE_DESCRIPTOR_TRAVERSAL:
        workspace_fd = _open_workspace_directory(workspace)
        try:
            walk_fd(workspace_fd)
        finally:
            os.close(workspace_fd)
    else:
        walk_path(workspace)

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

    if _SECURE_DESCRIPTOR_TRAVERSAL:
        final_stat, sample = _secure_preview_sample(workspace, parts, relative_path)
    else:
        final_stat, sample = _path_preview_sample(workspace, parts, relative_path)

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


def _secure_preview_sample(
    workspace: Path,
    parts: tuple[str, ...],
    relative_path: str,
) -> tuple[os.stat_result, bytes]:
    directory_fd = _open_workspace_directory(workspace)
    owned_fds = [directory_fd]
    try:
        for index, part in enumerate(parts[:-1]):
            relative = PurePosixPath(*parts[: index + 1]).as_posix()
            directory_fd = _open_directory_at(part, directory_fd, relative)
            owned_fds.append(directory_fd)
        file_fd = _open_file_at(parts[-1], directory_fd, relative_path)
        owned_fds.append(file_fd)
        final_stat = os.fstat(file_fd)
        if not stat.S_ISREG(final_stat.st_mode):
            raise ValueError("workspace preview requires a regular file")
        sample = _read_fd(file_fd, _MAX_PREVIEW_BYTES)
        return final_stat, sample
    finally:
        for fd in reversed(owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass


def _path_preview_sample(
    workspace: Path,
    parts: tuple[str, ...],
    relative_path: str,
) -> tuple[os.stat_result, bytes]:
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
    return final_stat, sample


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
            raise TypeError("audit attachment metadata is invalid")
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
        raise TypeError("workspace path must be text")
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


def _open_workspace_directory(workspace: Path) -> int:
    try:
        fd = os.open(workspace, _DIRECTORY_FLAGS)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError("replication workspace root must remain a real directory") from exc
        if exc.errno == errno.ENOENT:
            raise FileNotFoundError(f"replication workspace not found: {workspace.name}") from exc
        raise RuntimeError(f"unable to open replication workspace: {workspace.name}") from exc
    root_stat = os.fstat(fd)
    if not stat.S_ISDIR(root_stat.st_mode):
        os.close(fd)
        raise ValueError("replication workspace root must be a real directory")
    return fd


def _open_directory_at(name: str, directory_fd: int, relative: str) -> int:
    try:
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=directory_fd)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError(f"symlink or non-directory workspace path cannot be traversed: {relative}") from exc
        if exc.errno == errno.ENOENT:
            raise FileNotFoundError(f"workspace file not found: {relative}") from exc
        raise RuntimeError(f"unable to open workspace directory: {relative}") from exc


def _open_file_at(name: str, directory_fd: int, relative: str) -> int:
    try:
        return os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(f"symlink workspace files cannot be opened: {relative}") from exc
        if exc.errno in {errno.ENOENT, errno.ENOTDIR}:
            raise FileNotFoundError(f"workspace file not found: {relative}") from exc
        raise RuntimeError(f"unable to open workspace file: {relative}") from exc


def _require_same_entry(before: os.stat_result, after: os.stat_result, relative: str) -> None:
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise RuntimeError(f"workspace entry changed during inspection: {relative}")


def _read_fd(fd: int, limit: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < limit:
        chunk = os.read(fd, min(64 * 1024, limit - len(chunks)))
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


def _file_sha256_fd(fd: int | None) -> str:
    if fd is None:
        raise RuntimeError("workspace file descriptor is unavailable")
    digest = sha256()
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        while True:
            chunk = os.read(fd, _HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    except OSError as exc:
        raise RuntimeError("unable to hash workspace file descriptor") from exc
    return digest.hexdigest()


def _file_sha256(path: Path | None) -> str:
    if path is None:
        raise RuntimeError("workspace file path is unavailable")
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RuntimeError(f"unable to hash workspace file: {path.name}") from exc
    return digest.hexdigest()
