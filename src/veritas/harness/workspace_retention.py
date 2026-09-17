from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import HarnessEvent
from .store import HarnessStore

WORKSPACE_RETENTION_SCHEMA_VERSION = "1"
_TERMINAL_PHASES = frozenset({"finish", "error"})


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _run_id(value: object) -> str | None:
    if not isinstance(value, str) or not value.startswith("run_"):
        return None
    suffix = value[4:]
    if not suffix or not suffix.isalnum():
        return None
    return value


def _tree_size_no_follow(root: Path) -> int:
    if os.path.ismount(root):
        raise ValueError("workspace root must not be a mount point")
    total = 0
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                stat = entry.stat(follow_symlinks=False)
                if entry.is_symlink():
                    total += stat.st_size
                elif entry.is_dir(follow_symlinks=False):
                    child = Path(entry.path)
                    if os.path.ismount(child):
                        raise ValueError("workspace contains a mount point")
                    pending.append(child)
                else:
                    total += stat.st_size
    return total


def _remove_tree(root: Path) -> None:
    def make_writable_and_retry(function, path, _exc_info) -> None:
        os.chmod(path, 0o700)
        function(path)

    shutil.rmtree(root, onerror=make_writable_and_retry)


class WorkspaceRetention:
    """Operator-controlled retention for completed replication workspaces.

    Audit records, immutable source artifacts, and run traces are never deleted.
    Workspace age comes from persisted terminal run events rather than filesystem
    mtimes, which may be changed by the replication process itself.
    """

    def __init__(self, store: HarnessStore) -> None:
        self.store = store

    def list_workspaces(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        reference = self._normalized_now(now)
        workspaces: list[dict[str, Any]] = []
        for audit_dir in sorted(self.store.root.glob("audit_*"), key=lambda path: path.name):
            if not audit_dir.is_dir() or audit_dir.is_symlink():
                continue
            audit_id = audit_dir.name
            record = self.store.get_audit(audit_id)
            terminal = self._terminal_runs(record)
            running = self._running_runs(record, terminal)
            workspace_root = audit_dir / "replication-workspaces"
            if not workspace_root.exists():
                continue
            if workspace_root.is_symlink() or not workspace_root.is_dir():
                raise ValueError(f"invalid replication workspace root: {audit_id}")
            for workspace in sorted(workspace_root.iterdir(), key=lambda path: path.name):
                workspaces.append(
                    self._inspect_workspace(
                        audit_id,
                        workspace,
                        terminal=terminal,
                        running=running,
                        now=reference,
                    )
                )
        workspaces.sort(key=lambda item: (str(item["audit_id"]), str(item["run_id"])))
        return workspaces

    def prune(
        self,
        *,
        older_than_hours: int,
        apply: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if isinstance(older_than_hours, bool) or not isinstance(older_than_hours, int):
            raise TypeError("older_than_hours must be an integer")
        if older_than_hours < 1:
            raise ValueError("older_than_hours must be at least 1")

        reference = self._normalized_now(now)
        cutoff = reference - timedelta(hours=older_than_hours)
        inspected = self.list_workspaces(now=reference)
        for item in inspected:
            self._apply_eligibility(item, cutoff=cutoff)

        deleted: list[dict[str, Any]] = []
        if apply:
            for item in inspected:
                if not item["eligible"]:
                    continue
                refreshed = self._refresh_candidate(
                    str(item["audit_id"]),
                    str(item["run_id"]),
                    now=reference,
                    cutoff=cutoff,
                )
                if not refreshed["eligible"]:
                    item.update(refreshed)
                    continue
                self._delete_with_provenance(refreshed, older_than_hours=older_than_hours)
                refreshed["deleted"] = True
                deleted.append(refreshed)
                item.update(refreshed)

        candidates = [item for item in inspected if item["eligible"]]
        return {
            "schema_version": WORKSPACE_RETENTION_SCHEMA_VERSION,
            "apply": apply,
            "automatic_cleanup": False,
            "older_than_hours": older_than_hours,
            "workspace_count": len(inspected),
            "candidate_count": len(candidates),
            "deleted_count": len(deleted),
            "workspaces": inspected,
        }

    def _refresh_candidate(
        self,
        audit_id: str,
        run_id: str,
        *,
        now: datetime,
        cutoff: datetime,
    ) -> dict[str, Any]:
        record = self.store.get_audit(audit_id)
        terminal = self._terminal_runs(record)
        running = self._running_runs(record, terminal)
        workspace = self.store.root / audit_id / "replication-workspaces" / run_id
        item = self._inspect_workspace(
            audit_id,
            workspace,
            terminal=terminal,
            running=running,
            now=now,
        )
        self._apply_eligibility(item, cutoff=cutoff)
        return item

    def _inspect_workspace(
        self,
        audit_id: str,
        workspace: Path,
        *,
        terminal: dict[str, dict[str, Any]],
        running: set[str],
        now: datetime,
    ) -> dict[str, Any]:
        run_id = _run_id(workspace.name)
        item: dict[str, Any] = {
            "audit_id": audit_id,
            "run_id": workspace.name,
            "terminal_phase": None,
            "terminal_at": None,
            "age_hours": None,
            "size_bytes": None,
            "integrity": "invalid",
            "state": "unknown",
            "eligible": False,
            "deleted": False,
            "reason": "workspace is not a valid replication run directory",
        }
        if run_id is None:
            return item
        if not workspace.exists():
            item["reason"] = "workspace no longer exists"
            return item
        if workspace.is_symlink() or not workspace.is_dir():
            item["reason"] = "workspace root must be a real directory"
            return item

        manifest_path = workspace / "artifacts.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            item["reason"] = "artifacts manifest is missing or not a regular file"
            return item
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            item["reason"] = "artifacts manifest is unreadable"
            return item
        if not isinstance(manifest, dict):
            item["reason"] = "artifacts manifest must be an object"
            return item
        if manifest.get("schema_version") != "1" or manifest.get("run_id") != run_id:
            item["reason"] = "artifacts manifest does not match workspace run id"
            return item
        try:
            item["size_bytes"] = _tree_size_no_follow(workspace)
        except ValueError as exc:
            item["reason"] = str(exc)
            return item
        except OSError:
            item["reason"] = "workspace size could not be inspected safely"
            return item

        item["integrity"] = "valid"
        if run_id in terminal:
            event = terminal[run_id]
            item["state"] = "terminal"
            item["terminal_phase"] = event["phase"]
            item["terminal_at"] = event["created_at"]
            terminal_at = event["created_at_dt"]
            item["age_hours"] = max(0.0, (now - terminal_at).total_seconds() / 3600)
            item["reason"] = "terminal workspace"
        elif run_id in running:
            item["state"] = "running"
            item["reason"] = "replication run has no persisted terminal event"
        else:
            item["reason"] = "no persisted replication run matches workspace"
        return item

    @staticmethod
    def _apply_eligibility(item: dict[str, Any], *, cutoff: datetime) -> None:
        if item["integrity"] != "valid" or item["state"] != "terminal":
            item["eligible"] = False
            return
        try:
            terminal_at = _parse_timestamp(item["terminal_at"])
        except (TypeError, ValueError):
            item["integrity"] = "invalid"
            item["reason"] = "terminal event timestamp is invalid"
            item["eligible"] = False
            return
        if terminal_at > cutoff:
            item["eligible"] = False
            item["reason"] = "terminal workspace is newer than retention cutoff"
            return
        item["eligible"] = True
        item["reason"] = "terminal workspace is older than retention cutoff"

    def _delete_with_provenance(self, item: dict[str, Any], *, older_than_hours: int) -> None:
        audit_id = str(item["audit_id"])
        run_id = str(item["run_id"])
        payload = {
            "action": "replication_workspace_prune",
            "workspace_retention_schema_version": WORKSPACE_RETENTION_SCHEMA_VERSION,
            "target_run_id": run_id,
            "terminal_phase": item["terminal_phase"],
            "terminal_at": item["terminal_at"],
            "size_bytes": item["size_bytes"],
            "older_than_hours": older_than_hours,
            "automatic": False,
        }
        started = HarnessEvent(
            audit_id=audit_id,
            kind="maintenance",
            title="Replication workspace prune started",
            detail="Deleting one completed run workspace while preserving the audit trace and source artifacts.",
            status="running",
            payload={**payload, "phase": "start"},
        )
        self.store.append_event(started)

        workspace = self.store.root / audit_id / "replication-workspaces" / run_id
        try:
            if workspace.is_symlink() or not workspace.is_dir():
                raise ValueError("workspace changed before deletion")
            _tree_size_no_follow(workspace)
            _remove_tree(workspace)
        except (OSError, ValueError) as exc:
            failed = HarnessEvent(
                audit_id=audit_id,
                kind="maintenance",
                title="Replication workspace prune failed",
                detail=f"{type(exc).__name__}: {exc}",
                status="danger",
                payload={**payload, "phase": "error", "error_type": type(exc).__name__},
            )
            self.store.append_event(failed)
            raise

        finished = HarnessEvent(
            audit_id=audit_id,
            kind="maintenance",
            title="Replication workspace pruned",
            detail="Completed run workspace deleted; immutable source artifacts and persisted run trace retained.",
            status="success",
            payload={**payload, "phase": "finish"},
        )
        self.store.append_event(finished)

    @staticmethod
    def _terminal_runs(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
        terminal: dict[str, dict[str, Any]] = {}
        for event in record.get("events") or []:
            if not isinstance(event, dict) or event.get("kind") != "tool":
                continue
            payload = event.get("payload") or {}
            if not isinstance(payload, dict) or payload.get("run_kind") != "replication":
                continue
            run_id = _run_id(payload.get("run_id"))
            phase = payload.get("phase")
            if run_id is None or phase not in _TERMINAL_PHASES:
                continue
            try:
                created_at_dt = _parse_timestamp(event.get("created_at"))
            except (TypeError, ValueError):
                continue
            candidate = {
                "phase": phase,
                "created_at": event.get("created_at"),
                "created_at_dt": created_at_dt,
            }
            previous = terminal.get(run_id)
            if previous is None or created_at_dt > previous["created_at_dt"]:
                terminal[run_id] = candidate
        return terminal

    @staticmethod
    def _running_runs(record: dict[str, Any], terminal: dict[str, dict[str, Any]]) -> set[str]:
        running: set[str] = set()
        for event in record.get("events") or []:
            if not isinstance(event, dict) or event.get("kind") != "tool":
                continue
            payload = event.get("payload") or {}
            if not isinstance(payload, dict) or payload.get("run_kind") != "replication":
                continue
            run_id = _run_id(payload.get("run_id"))
            if run_id is not None and payload.get("phase") == "start" and run_id not in terminal:
                running.add(run_id)
        return running

    @staticmethod
    def _normalized_now(value: datetime | None) -> datetime:
        current = value or datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must include a timezone")
        return current.astimezone(UTC)
