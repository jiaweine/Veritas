from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def _make_pdf(label: str = "Replication workspace paper") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), label, fontsize=14)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _create_audit(client: TestClient, title: str = "Workspace paper") -> str:
    response = client.post(
        "/api/v1/audits",
        data={"title": title},
        files={"file": ("paper.pdf", _make_pdf(title), "application/pdf")},
    )
    assert response.status_code == 200
    return str(response.json()["audit_id"])


def _run_id(response) -> str:
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    ids = {event["payload"]["run_id"] for event in events if event.get("payload", {}).get("run_id")}
    assert len(ids) == 1
    return ids.pop()


def _configure_runner(monkeypatch, runner_type) -> None:
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "fake-agent --stdio")
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT_NAME", "Workspace test agent")
    monkeypatch.delenv("VERITAS_REPLICATION_PERMISSION_POLICY", raising=False)
    monkeypatch.setattr("veritas.harness.service.AcpTurnRunner", runner_type)


def test_workspace_snapshot_and_preview_are_run_scoped_and_path_safe(tmp_path, monkeypatch) -> None:
    symlink_created = False

    class FakeRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace: Path, prompt: str):
            nonlocal symlink_created
            assert prompt == "Reproduce the result."
            output = workspace / "outputs"
            output.mkdir()
            (output / "result.txt").write_text("estimate=0.100\nstatus=matched\n", encoding="utf-8")
            (output / "binary.bin").write_bytes(b"\x00\x01\x02")
            try:
                os.symlink(workspace.parent.parent / "audit.json", output / "outside-link")
                symlink_created = True
            except OSError:
                pass
            yield {
                "event_id": "rep_workspace_evt",
                "kind": "agent_update",
                "title": "tool_call_update",
                "detail": "Wrote reproduction outputs.",
                "status": "success",
                "payload": {},
                "created_at": "2026-09-29T00:00:00Z",
            }

    _configure_runner(monkeypatch, FakeRunner)
    client = TestClient(create_app(tmp_path))
    audit_id = _create_audit(client)
    attachment_bytes = b"print('immutable input')\n"
    attached = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={"file": ("analysis.py", attachment_bytes, "text/x-python")},
    )
    assert attached.status_code == 200
    attachment = attached.json()
    assert attachment["sha256"] == sha256(attachment_bytes).hexdigest()

    run_id = _run_id(
        client.post(
            f"/api/v1/audits/{audit_id}/replication",
            json={"prompt": "Reproduce the result."},
        )
    )

    snapshot_response = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace"
    )
    assert snapshot_response.status_code == 200
    assert snapshot_response.headers["cache-control"] == "no-store"
    snapshot = snapshot_response.json()
    assert snapshot["audit_id"] == audit_id
    assert snapshot["run_id"] == run_id
    assert snapshot["workspace_is_security_boundary"] is False
    assert snapshot["integrity_scope"] == "veritas_staged_inputs_only"
    assert snapshot["integrity_ok"] is True
    assert snapshot["summary"]["staged_modified"] == 0
    assert snapshot["summary"]["staged_deleted"] == 0
    assert snapshot["summary"]["created_files"] == 2
    assert snapshot["summary"]["staged_unchanged"] == 3

    by_path = {item["path"]: item for item in snapshot["files"]}
    assert by_path["paper.pdf"]["status"] == "staged_unchanged"
    assert by_path["artifacts.json"]["status"] == "staged_unchanged"
    attachment_path = f'attachments/{attachment["attachment_id"]}/analysis.py'
    assert by_path[attachment_path]["status"] == "staged_unchanged"
    assert by_path["outputs/result.txt"]["status"] == "created"
    assert by_path["outputs/result.txt"]["hash_computed"] is True
    if symlink_created:
        assert by_path["outputs/outside-link"]["kind"] == "symlink"
        assert by_path["outputs/outside-link"]["status"] == "created_symlink"
        symlink_preview = client.get(
            f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace/file",
            params={"path": "outputs/outside-link"},
        )
        assert symlink_preview.status_code == 422

    preview = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace/file",
        params={"path": "outputs/result.txt"},
    )
    assert preview.status_code == 200
    assert preview.json()["previewable"] is True
    assert preview.json()["encoding"] == "utf-8"
    assert "estimate=0.100" in preview.json()["content"]

    binary = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace/file",
        params={"path": "outputs/binary.bin"},
    )
    assert binary.status_code == 200
    assert binary.json()["previewable"] is False
    assert binary.json()["reason"] == "binary_content"

    traversal = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace/file",
        params={"path": "../audit.json"},
    )
    assert traversal.status_code == 422
    absolute = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace/file",
        params={"path": "/etc/passwd"},
    )
    assert absolute.status_code == 422
    unstaged_parent_file = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace/file",
        params={"path": "audit.json"},
    )
    assert unstaged_parent_file.status_code == 404

    other_audit = _create_audit(client, "Other audit")
    wrong_owner = client.get(
        f"/api/v1/audits/{other_audit}/replication-runs/{run_id}/workspace"
    )
    assert wrong_owner.status_code == 404
    unknown_valid_run = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/run_aaaaaaaaaaaa/workspace"
    )
    assert unknown_valid_run.status_code == 404
    malformed_run = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/not-a-run/workspace"
    )
    assert malformed_run.status_code == 422


def test_workspace_snapshot_detects_post_start_staged_mutation_and_deletion(tmp_path, monkeypatch) -> None:
    attachment_path_from_manifest = ""

    class MutatingRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace: Path, prompt: str):
            nonlocal attachment_path_from_manifest
            manifest = json.loads((workspace / "artifacts.json").read_text(encoding="utf-8"))
            attachment_path_from_manifest = manifest["attachments"][0]["path"]
            paper = workspace / "paper.pdf"
            paper.chmod(0o644)
            paper.write_bytes(b"post-start workspace mutation")
            (workspace / attachment_path_from_manifest).unlink()
            (workspace / "generated.txt").write_text("untrusted output\n", encoding="utf-8")
            yield {
                "event_id": "rep_mutation_evt",
                "kind": "agent_update",
                "title": "tool_call_update",
                "detail": "Mutated staged inputs.",
                "status": "review",
                "payload": {},
                "created_at": "2026-09-29T00:00:00Z",
            }

    _configure_runner(monkeypatch, MutatingRunner)
    client = TestClient(create_app(tmp_path))
    audit_id = _create_audit(client)
    attached = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={"file": ("analysis.py", b"print('input')\n", "text/x-python")},
    )
    assert attached.status_code == 200

    run_id = _run_id(
        client.post(
            f"/api/v1/audits/{audit_id}/replication",
            json={"prompt": "Try a hostile reproduction."},
        )
    )
    snapshot = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace"
    ).json()

    assert snapshot["integrity_ok"] is False
    assert snapshot["summary"]["staged_modified"] == 1
    assert snapshot["summary"]["staged_deleted"] == 1
    by_path = {item["path"]: item for item in snapshot["files"]}
    assert by_path["paper.pdf"]["status"] == "staged_modified"
    assert by_path[attachment_path_from_manifest]["status"] == "staged_deleted"
    assert by_path["generated.txt"]["status"] == "created"
    assert "untrusted reproduction outputs" in snapshot["note"]

    runtime = client.app.state.harness
    assert runtime.store.get_pdf_path(audit_id).read_bytes().startswith(b"%PDF")
    attachment_id = attached.json()["attachment_id"]
    assert runtime.store.get_attachment_path(audit_id, attachment_id).read_bytes() == b"print('input')\n"


def test_workspace_snapshot_fails_bounded_on_excessive_entry_count(tmp_path, monkeypatch) -> None:
    class ManyFilesRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace: Path, prompt: str):
            output = workspace / "many"
            output.mkdir()
            for index in range(1001):
                (output / f"{index:04d}.txt").write_text("x", encoding="utf-8")
            if False:
                yield {}

    _configure_runner(monkeypatch, ManyFilesRunner)
    client = TestClient(create_app(tmp_path))
    audit_id = _create_audit(client)
    run_id = _run_id(
        client.post(
            f"/api/v1/audits/{audit_id}/replication",
            json={"prompt": "Generate too many outputs."},
        )
    )

    response = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace"
    )
    assert response.status_code == 413
    assert "1000-entry inspection limit" in response.json()["detail"]
