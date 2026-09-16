from __future__ import annotations

import json

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Replication artifact integrity test", fontsize=14)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_tampered_attachment_becomes_persisted_replication_error(tmp_path, monkeypatch) -> None:
    class FakeRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace, prompt):
            raise AssertionError("ACP runner must not start when artifact integrity fails")
            yield  # pragma: no cover

    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "fake-agent --stdio")
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT_NAME", "Integrity test agent")
    monkeypatch.delenv("VERITAS_REPLICATION_PERMISSION_POLICY", raising=False)
    monkeypatch.setattr("veritas.harness.service.AcpTurnRunner", FakeRunner)

    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Integrity test paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    audit_id = created.json()["audit_id"]

    attached = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={"file": ("analysis.py", b"print('expected')\n", "text/x-python")},
    )
    assert attached.status_code == 200
    attachment_id = attached.json()["attachment_id"]

    runtime = client.app.state.harness
    attachment_path = runtime.store.get_attachment_path(audit_id, attachment_id)
    attachment_path.chmod(0o644)
    attachment_path.write_bytes(b"print('tampered')\n")

    prompt = "Reproduce the main result using the attached analysis code."
    response = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={"prompt": prompt},
    )
    assert response.status_code == 200

    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [event["kind"] for event in events] == ["tool", "tool"]
    assert [event["payload"]["phase"] for event in events] == ["start", "error"]
    assert events[0]["payload"]["stage"] == "workspace_prepare"
    assert events[1]["payload"]["stage"] == "workspace_prepare"
    assert events[1]["payload"]["error_type"] == "ValueError"
    assert "hash mismatch" in events[1]["detail"]
    assert prompt not in json.dumps(events[0], ensure_ascii=False)

    run_ids = {event["payload"]["run_id"] for event in events}
    assert len(run_ids) == 1
    run_id = run_ids.pop()

    runs = client.get("/api/v1/runs").json()
    failed_run = next(run for run in runs if run["run_id"] == run_id)
    assert failed_run["run_kind"] == "replication"
    assert failed_run["phase"] == "error"
    assert failed_run["error_type"] == "ValueError"

    detail = client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["run_id"] == run_id
    assert payload["phase"] == "error"
    assert [event["payload"]["phase"] for event in payload["events"]] == ["start", "error"]
