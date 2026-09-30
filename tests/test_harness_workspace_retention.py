from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from veritas.harness import workspace_cli
from veritas.harness.models import HarnessEvent
from veritas.harness.store import HarnessStore
from veritas.harness.workspace_retention import WorkspaceRetention


def _create_audit(store: HarnessStore) -> str:
    record = store.create_audit(
        title="Retention test",
        filename="paper.pdf",
        pdf_bytes=b"%PDF-1.7\nretention-test\n",
        paper_summary={"artifact_id": "paper-retention-test", "pages": 1},
    )
    return str(record["audit_id"])


def _create_workspace(
    store: HarnessStore,
    audit_id: str,
    run_id: str,
    *,
    manifest_run_id: str | None = None,
) -> Path:
    workspace = store.root / audit_id / "replication-workspaces" / run_id
    workspace.mkdir(parents=True)
    (workspace / "paper.pdf").write_bytes(b"%PDF-1.7\nworkspace-copy\n")
    (workspace / "agent-output.txt").write_text("result\n", encoding="utf-8")
    (workspace / "artifacts.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "run_id": manifest_run_id or run_id,
                "paper": {"filename": "paper.pdf"},
                "attachments": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return workspace


def _append_run_event(
    store: HarnessStore,
    audit_id: str,
    run_id: str,
    *,
    phase: str,
    created_at: str,
) -> None:
    store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Replication run",
            status="success" if phase == "finish" else "running",
            created_at=created_at,
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": phase,
            },
        )
    )


def test_retention_uses_persisted_terminal_time_not_workspace_mtime(tmp_path: Path) -> None:
    store = HarnessStore(tmp_path)
    audit_id = _create_audit(store)
    run_id = "run_oldterminal"
    workspace = _create_workspace(store, audit_id, run_id)
    _append_run_event(
        store,
        audit_id,
        run_id,
        phase="finish",
        created_at="2026-09-14T12:00:00Z",
    )

    now = datetime(2026, 9, 17, 12, tzinfo=UTC)
    os.utime(workspace, (now.timestamp(), now.timestamp()))
    result = WorkspaceRetention(store).prune(older_than_hours=24, now=now)

    assert result["apply"] is False
    assert result["candidate_count"] == 1
    item = result["workspaces"][0]
    assert item["run_id"] == run_id
    assert item["state"] == "terminal"
    assert item["age_hours"] == 72.0
    assert item["eligible"] is True
    assert workspace.is_dir()


def test_prune_dry_run_has_no_side_effects(tmp_path: Path) -> None:
    store = HarnessStore(tmp_path)
    audit_id = _create_audit(store)
    run_id = "run_dryrun"
    workspace = _create_workspace(store, audit_id, run_id)
    _append_run_event(
        store,
        audit_id,
        run_id,
        phase="error",
        created_at="2026-09-10T00:00:00Z",
    )
    before_events = list(store.get_audit(audit_id)["events"])

    result = WorkspaceRetention(store).prune(
        older_than_hours=24,
        apply=False,
        now=datetime(2026, 9, 17, 12, tzinfo=UTC),
    )

    assert result["candidate_count"] == 1
    assert result["deleted_count"] == 0
    assert workspace.is_dir()
    assert store.get_audit(audit_id)["events"] == before_events


def test_apply_prunes_only_old_terminal_valid_workspace(tmp_path: Path) -> None:
    store = HarnessStore(tmp_path)
    audit_id = _create_audit(store)
    old_run = "run_old"
    new_run = "run_new"
    running_run = "run_running"
    unknown_run = "run_unknown"
    malformed_run = "run_malformed"

    old_workspace = _create_workspace(store, audit_id, old_run)
    new_workspace = _create_workspace(store, audit_id, new_run)
    running_workspace = _create_workspace(store, audit_id, running_run)
    unknown_workspace = _create_workspace(store, audit_id, unknown_run)
    malformed_workspace = _create_workspace(
        store,
        audit_id,
        malformed_run,
        manifest_run_id="run_other",
    )

    _append_run_event(
        store,
        audit_id,
        old_run,
        phase="finish",
        created_at="2026-09-10T00:00:00Z",
    )
    _append_run_event(
        store,
        audit_id,
        new_run,
        phase="finish",
        created_at="2026-09-17T06:00:00Z",
    )
    _append_run_event(
        store,
        audit_id,
        running_run,
        phase="start",
        created_at="2026-09-01T00:00:00Z",
    )

    result = WorkspaceRetention(store).prune(
        older_than_hours=24,
        apply=True,
        now=datetime(2026, 9, 17, 12, tzinfo=UTC),
    )

    assert result["candidate_count"] == 1
    assert result["deleted_count"] == 1
    assert not old_workspace.exists()
    assert new_workspace.is_dir()
    assert running_workspace.is_dir()
    assert unknown_workspace.is_dir()
    assert malformed_workspace.is_dir()

    paper_path = store.get_pdf_path(audit_id)
    assert paper_path.is_file()
    record = store.get_audit(audit_id)
    maintenance = [event for event in record["events"] if event["kind"] == "maintenance"]
    assert [event["payload"]["phase"] for event in maintenance] == ["start", "finish"]
    assert all(event["payload"]["target_run_id"] == old_run for event in maintenance)
    assert all(event["payload"]["automatic"] is False for event in maintenance)
    assert str(store.root) not in json.dumps(maintenance)

    by_run = {item["run_id"]: item for item in result["workspaces"]}
    assert by_run[new_run]["reason"] == "terminal workspace is newer than retention cutoff"
    assert by_run[running_run]["state"] == "running"
    assert by_run[unknown_run]["state"] == "unknown"
    assert by_run[malformed_run]["integrity"] == "invalid"


def test_manifest_run_id_mismatch_fails_closed(tmp_path: Path) -> None:
    store = HarnessStore(tmp_path)
    audit_id = _create_audit(store)
    run_id = "run_manifestmismatch"
    workspace = _create_workspace(store, audit_id, run_id, manifest_run_id="run_other")
    _append_run_event(
        store,
        audit_id,
        run_id,
        phase="finish",
        created_at="2026-09-01T00:00:00Z",
    )

    result = WorkspaceRetention(store).prune(
        older_than_hours=1,
        apply=True,
        now=datetime(2026, 9, 17, 12, tzinfo=UTC),
    )

    assert result["candidate_count"] == 0
    assert result["deleted_count"] == 0
    assert workspace.is_dir()
    item = result["workspaces"][0]
    assert item["integrity"] == "invalid"
    assert item["eligible"] is False


def test_workspace_mountpoint_fails_closed(tmp_path: Path, monkeypatch) -> None:
    store = HarnessStore(tmp_path)
    audit_id = _create_audit(store)
    run_id = "run_mounted"
    workspace = _create_workspace(store, audit_id, run_id)
    mounted = workspace / "mounted-output"
    mounted.mkdir()
    _append_run_event(
        store,
        audit_id,
        run_id,
        phase="finish",
        created_at="2026-09-01T00:00:00Z",
    )

    original_ismount = os.path.ismount
    monkeypatch.setattr(
        os.path,
        "ismount",
        lambda path: Path(path) == mounted or original_ismount(path),
    )
    result = WorkspaceRetention(store).prune(
        older_than_hours=1,
        apply=True,
        now=datetime(2026, 9, 17, 12, tzinfo=UTC),
    )

    assert result["candidate_count"] == 0
    assert result["deleted_count"] == 0
    assert workspace.is_dir()
    item = result["workspaces"][0]
    assert item["integrity"] == "invalid"
    assert item["reason"] == "workspace contains a mount point"


def test_workspace_cli_is_dry_run_unless_apply_is_explicit(tmp_path: Path) -> None:
    store = HarnessStore(tmp_path)
    audit_id = _create_audit(store)
    run_id = "run_cli"
    workspace = _create_workspace(store, audit_id, run_id)
    _append_run_event(
        store,
        audit_id,
        run_id,
        phase="finish",
        created_at="2020-01-01T00:00:00Z",
    )

    dry_args = argparse.Namespace(
        data_dir=str(tmp_path),
        command="prune",
        older_than_hours=24,
        apply=False,
    )
    dry = workspace_cli.run(dry_args)
    assert dry["candidate_count"] == 1
    assert dry["deleted_count"] == 0
    assert workspace.is_dir()

    apply_args = argparse.Namespace(
        data_dir=str(tmp_path),
        command="prune",
        older_than_hours=24,
        apply=True,
    )
    applied = workspace_cli.run(apply_args)
    assert applied["deleted_count"] == 1
    assert not workspace.exists()


def test_workspace_cli_does_not_create_missing_data_dir(tmp_path: Path) -> None:
    missing = tmp_path / "not-created"

    listed = workspace_cli.run(argparse.Namespace(data_dir=str(missing), command="list"))
    dry = workspace_cli.run(
        argparse.Namespace(
            data_dir=str(missing),
            command="prune",
            older_than_hours=24,
            apply=False,
        )
    )

    assert listed["workspace_count"] == 0
    assert dry["workspace_count"] == 0
    assert dry["candidate_count"] == 0
    assert not missing.exists()
