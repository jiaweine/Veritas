from __future__ import annotations

import json
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Bounded workspace diff paper", fontsize=14)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _run_id(response) -> str:
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    ids = {
        event["payload"]["run_id"]
        for event in events
        if event.get("payload", {}).get("run_id")
    }
    assert len(ids) == 1
    return ids.pop()


def test_product_workspace_file_exposes_bounded_text_diffs(tmp_path, monkeypatch) -> None:
    paths: dict[str, str] = {}

    class DiffRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace: Path, prompt: str):
            manifest = json.loads((workspace / "artifacts.json").read_text(encoding="utf-8"))
            by_name = {item["filename"]: item["path"] for item in manifest["attachments"]}
            paths.update(by_name)

            modified = workspace / by_name["model.txt"]
            modified.chmod(0o644)
            modified.write_text("alpha\ngamma\n", encoding="utf-8")

            deleted = workspace / by_name["delete.txt"]
            deleted.unlink()

            output = workspace / "outputs"
            output.mkdir()
            (output / "new.txt").write_text("created\n", encoding="utf-8")
            (output / "large.txt").write_text("x" * (256 * 1024 + 1), encoding="utf-8")

            yield {
                "event_id": "rep_diff_evt",
                "kind": "agent_update",
                "title": "tool_call_update",
                "detail": "Changed workspace text files.",
                "status": "review",
                "payload": {},
                "created_at": "2026-09-30T00:00:00Z",
            }

    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "fake-agent --stdio")
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT_NAME", "Diff test agent")
    monkeypatch.delenv("VERITAS_REPLICATION_PERMISSION_POLICY", raising=False)
    monkeypatch.setattr("veritas.harness.service.AcpTurnRunner", DiffRunner)

    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Diff paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    audit_id = created.json()["audit_id"]

    originals = {
        "model.txt": b"alpha\nbeta\n",
        "delete.txt": b"keep\n",
    }
    attachments: dict[str, dict] = {}
    for filename, payload in originals.items():
        response = client.post(
            f"/api/v1/audits/{audit_id}/attachments",
            files={"file": (filename, payload, "text/plain")},
        )
        assert response.status_code == 200
        attachments[filename] = response.json()

    run_id = _run_id(
        client.post(
            f"/api/v1/audits/{audit_id}/replication",
            json={"prompt": "Exercise bounded text diff inspection."},
        )
    )

    snapshot = client.get(f"/api/v1/runs/{run_id}/workspace")
    assert snapshot.status_code == 200
    assert snapshot.json()["counts"]["modified"] == 1
    assert snapshot.json()["counts"]["deleted"] == 1
    assert snapshot.json()["counts"]["created"] == 2

    modified = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": paths["model.txt"]},
    )
    assert modified.status_code == 200
    modified_value = modified.json()
    assert modified_value["change"] == "modified"
    assert modified_value["diff_available"] is True
    assert modified_value["diff_baseline"] == "immutable_source"
    assert modified_value["diff_reason"] is None
    assert f"--- a/{paths['model.txt']}" in modified_value["diff"]
    assert f"+++ b/{paths['model.txt']}" in modified_value["diff"]
    assert "-beta" in modified_value["diff"]
    assert "+gamma" in modified_value["diff"]

    deleted = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": paths["delete.txt"]},
    )
    assert deleted.status_code == 200
    deleted_value = deleted.json()
    assert deleted_value["change"] == "deleted"
    assert deleted_value["previewable"] is False
    assert deleted_value["reason"] == "workspace_file_deleted"
    assert deleted_value["diff_available"] is True
    assert f"--- a/{paths['delete.txt']}" in deleted_value["diff"]
    assert "+++ /dev/null" in deleted_value["diff"]
    assert "-keep" in deleted_value["diff"]

    created_file = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": "outputs/new.txt"},
    ).json()
    assert created_file["change"] == "created"
    assert created_file["diff_available"] is True
    assert created_file["diff_baseline"] == "empty"
    assert "--- /dev/null" in created_file["diff"]
    assert "+++ b/outputs/new.txt" in created_file["diff"]
    assert "+created" in created_file["diff"]

    large_file = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": "outputs/large.txt"},
    ).json()
    assert large_file["truncated"] is True
    assert large_file["diff_available"] is False
    assert large_file["diff"] == ""
    assert large_file["diff_reason"] == "current_too_large"
    assert large_file["diff_input_limit_bytes"] == 256 * 1024
    assert large_file["diff_output_limit_bytes"] == 512 * 1024

    runtime = client.app.state.harness
    for filename, metadata in attachments.items():
        source = runtime.store.get_attachment_path(audit_id, metadata["attachment_id"])
        assert source.read_bytes() == originals[filename]

    raw_deleted = client.get(
        f"/api/v1/audits/{audit_id}/replication-runs/{run_id}/workspace/file",
        params={"path": paths["delete.txt"]},
    )
    assert raw_deleted.status_code == 404


def test_binary_staged_input_does_not_claim_a_text_diff(tmp_path, monkeypatch) -> None:
    attachment_path = ""

    class BinaryRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace: Path, prompt: str):
            nonlocal attachment_path
            manifest = json.loads((workspace / "artifacts.json").read_text(encoding="utf-8"))
            attachment_path = manifest["attachments"][0]["path"]
            target = workspace / attachment_path
            target.chmod(0o644)
            target.write_bytes(b"\x00changed")
            if False:
                yield {}

    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "fake-agent --stdio")
    monkeypatch.setattr("veritas.harness.service.AcpTurnRunner", BinaryRunner)

    client = TestClient(create_app(tmp_path))
    audit_id = client.post(
        "/api/v1/audits",
        data={"title": "Binary diff paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    ).json()["audit_id"]
    attached = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={"file": ("input.bin", b"\x00original", "application/octet-stream")},
    )
    assert attached.status_code == 200

    run_id = _run_id(
        client.post(
            f"/api/v1/audits/{audit_id}/replication",
            json={"prompt": "Mutate the binary input."},
        )
    )
    value = client.get(
        f"/api/v1/runs/{run_id}/workspace/file",
        params={"path": attachment_path},
    ).json()

    assert value["change"] == "modified"
    assert value["binary"] is True
    assert value["diff_available"] is False
    assert value["diff"] == ""
    assert value["diff_reason"] == "baseline_binary"
