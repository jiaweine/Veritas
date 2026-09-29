from __future__ import annotations

import json

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.web import create_app
from veritas.replication import ReplicationCancelledError


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Synthetic cancelled replication paper", fontsize=14)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_cancelled_replication_is_persisted_as_review_not_error(tmp_path, monkeypatch) -> None:
    class CancelledRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace, prompt):
            if False:
                yield {}
            raise ReplicationCancelledError("replication run cancelled by user")

    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "fake-agent --stdio")
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT_NAME", "Cancellation fixture")
    monkeypatch.setattr("veritas.harness.service.AcpTurnRunner", CancelledRunner)

    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Cancellation paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    audit_id = created.json()["audit_id"]

    response = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={"prompt": "Start then cancel this reproduction."},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    tool_events = [event for event in events if event["kind"] == "tool"]
    assert [event["payload"]["phase"] for event in tool_events] == ["start", "cancelled"]
    assert tool_events[-1]["title"] == "Replication run cancelled"
    assert tool_events[-1]["status"] == "review"
    assert tool_events[-1]["payload"]["result"]["status"] == "cancelled"
    assert "error_type" not in tool_events[-1]["payload"]

    run_id = tool_events[-1]["payload"]["run_id"]
    run = next(item for item in client.get("/api/v1/runs").json() if item["run_id"] == run_id)
    assert run["phase"] == "cancelled"
    assert run["status"] == "review"
    assert run["task"] == "Replication run cancelled"
    assert run["error_type"] is None

    detail = client.get(f"/api/v1/runs/{run_id}").json()
    assert detail["phase"] == "cancelled"
    assert detail["status"] == "review"
    assert detail["events"][-1]["payload"]["phase"] == "cancelled"

    overview = client.get("/api/v1/overview").json()
    cancellation_activity = next(
        item for item in overview["recent_activity"] if item["title"] == "Replication run cancelled"
    )
    assert cancellation_activity["status"] == "review"
