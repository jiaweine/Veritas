from __future__ import annotations

import json

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Synthetic finding replication paper", fontsize=14)
    page.insert_text((60, 112), "Table 4. Main result", fontsize=11)
    page.insert_text((60, 145), "Treatment  -0.021  (0.026)", fontsize=10)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_replication_run_binds_only_server_resolved_finding_context(tmp_path, monkeypatch) -> None:
    observed_prompts: list[str] = []

    class FakeRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace, prompt):
            observed_prompts.append(prompt)
            yield {
                "event_id": "rep_evt_binding",
                "kind": "agent_update",
                "title": "plan",
                "detail": "Locate the reproduction command and compare the result.",
                "status": "running",
                "payload": {"step": 1},
                "created_at": "2026-09-30T00:00:00Z",
            }

    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "fake-agent --stdio")
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT_NAME", "CI fake agent")
    monkeypatch.delenv("VERITAS_REPLICATION_PERMISSION_POLICY", raising=False)
    monkeypatch.setattr("veritas.harness.service.AcpTurnRunner", FakeRunner)

    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Finding replication paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    ).json()
    audit_id = created["audit_id"]
    finding_id = f"{audit_id}:finding:0"

    server_finding = {
        "finding_id": finding_id,
        "audit_id": audit_id,
        "audit_title": "Finding replication paper",
        "title": "Reported standard error needs review",
        "explanation": "Narrative and table values differ.",
        "severity": "needs_review",
        "source": {
            "table": "Table 4",
            "row": "Treatment",
            "column": "(1)",
            "page": 12,
            "ignored_nested": {"client": "must not persist"},
        },
    }
    runtime = client.app.state.harness
    monkeypatch.setattr(runtime, "findings", lambda: [server_finding])

    prompt = "Reproduce the Table 4 treatment estimate and compare it with the paper."
    response = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={"prompt": prompt, "finding_id": finding_id},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [event["kind"] for event in events] == [
        "tool",
        "replication_context",
        "replication",
        "tool",
    ]
    assert observed_prompts == [prompt]

    context_event = events[1]
    origin = context_event["payload"]["origin_finding"]
    assert origin == {
        "finding_id": finding_id,
        "title": "Reported standard error needs review",
        "severity": "needs_review",
        "source": {
            "page": 12,
            "table": "Table 4",
            "row": "Treatment",
            "column": "(1)",
        },
        "binding_only": True,
    }
    assert "does not resolve the finding" in context_event["detail"]
    assert "ignored_nested" not in json.dumps(origin)

    run_id = events[0]["payload"]["run_id"]
    detail = client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    run = detail.json()
    assert run["run_kind"] == "replication"
    assert run["evidence"] is False
    assert run["origin_finding"] == origin
    assert any(event["kind"] == "replication_context" for event in run["events"])

    invalid = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={"prompt": prompt, "finding_id": f"{audit_id}:finding:999"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "finding does not belong to this audit"
    assert observed_prompts == [prompt]
