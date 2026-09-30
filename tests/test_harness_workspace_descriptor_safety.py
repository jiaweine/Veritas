from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path

import pytest

from veritas.harness import replication_workspace as workspace_module
from veritas.harness.models import HarnessEvent
from veritas.harness.replication_workspace import (
    preview_replication_workspace_file,
    replication_workspace_snapshot,
)
from veritas.harness.store import HarnessStore


def _seed_workspace(tmp_path: Path) -> tuple[HarnessStore, str, str, Path]:
    store = HarnessStore(tmp_path / "harness")
    pdf_bytes = b"%PDF-1.7\n% descriptor-safety fixture\n%%EOF\n"
    artifact_id = "paper-descriptor-safety"
    record = store.create_audit(
        title="Descriptor safety",
        filename="paper.pdf",
        pdf_bytes=pdf_bytes,
        paper_summary={
            "artifact_id": artifact_id,
            "pages": 1,
            "tables_detected": 0,
            "words": 3,
        },
    )
    audit_id = str(record["audit_id"])
    run_id = "run_aaaaaaaaaaaa"
    store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Replication agent run",
            status="running",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "start",
            },
        )
    )

    workspace = store.root / audit_id / "replication-workspaces" / run_id
    workspace.mkdir(parents=True)
    (workspace / "paper.pdf").write_bytes(pdf_bytes)
    manifest = {
        "schema_version": "1",
        "run_id": run_id,
        "paper": {
            "filename": "paper.pdf",
            "sha256": sha256(pdf_bytes).hexdigest(),
            "artifact_id": artifact_id,
        },
        "attachments": [],
    }
    (workspace / "artifacts.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    output = workspace / "outputs"
    output.mkdir()
    (output / "result.txt").write_text("safe-result\n", encoding="utf-8")
    return store, audit_id, run_id, workspace


def test_preview_is_anchored_when_parent_path_is_swapped_after_open(
    tmp_path: Path,
    monkeypatch,
) -> None:
    if not workspace_module._SECURE_DESCRIPTOR_TRAVERSAL:
        pytest.skip("descriptor-relative no-follow traversal is unavailable on this platform")

    store, audit_id, run_id, workspace = _seed_workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "result.txt").write_text("outside-secret\n", encoding="utf-8")

    original_open_file_at = workspace_module._open_file_at
    swapped = False

    def swap_parent_then_open(name: str, directory_fd: int, relative: str) -> int:
        nonlocal swapped
        if relative == "outputs/result.txt" and not swapped:
            original = workspace / "outputs"
            parked = workspace / "outputs-original"
            original.rename(parked)
            try:
                os.symlink(outside, original, target_is_directory=True)
            except (NotImplementedError, OSError):
                parked.rename(original)
                pytest.skip("directory symlinks are unavailable on this platform")
            swapped = True
        return original_open_file_at(name, directory_fd, relative)

    monkeypatch.setattr(workspace_module, "_open_file_at", swap_parent_then_open)
    preview = preview_replication_workspace_file(
        store,
        audit_id,
        run_id,
        "outputs/result.txt",
    )

    assert swapped is True
    assert preview["previewable"] is True
    assert preview["content"] == "safe-result\n"
    assert "outside-secret" not in str(preview["content"])


def test_snapshot_fails_closed_if_file_becomes_symlink_between_stat_and_open(
    tmp_path: Path,
    monkeypatch,
) -> None:
    if not workspace_module._SECURE_DESCRIPTOR_TRAVERSAL:
        pytest.skip("descriptor-relative no-follow traversal is unavailable on this platform")

    store, audit_id, run_id, workspace = _seed_workspace(tmp_path)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside-secret\n", encoding="utf-8")
    target = workspace / "outputs" / "result.txt"

    original_open_file_at = workspace_module._open_file_at
    swapped = False

    def replace_with_symlink_then_open(name: str, directory_fd: int, relative: str) -> int:
        nonlocal swapped
        if relative == "outputs/result.txt" and not swapped:
            target.unlink()
            try:
                os.symlink(outside, target)
            except (NotImplementedError, OSError):
                target.write_text("safe-result\n", encoding="utf-8")
                pytest.skip("file symlinks are unavailable on this platform")
            swapped = True
        return original_open_file_at(name, directory_fd, relative)

    monkeypatch.setattr(workspace_module, "_open_file_at", replace_with_symlink_then_open)

    with pytest.raises(ValueError, match="symlink"):
        replication_workspace_snapshot(store, audit_id, run_id)
    assert swapped is True
