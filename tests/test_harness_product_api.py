from __future__ import annotations

import json

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Synthetic Product API Paper", fontsize=14)
    page.insert_text((60, 112), "Table 2. Main regression", fontsize=11)
    xs = (72, 220, 300, 380, 460, 540)
    ys = (140, 170, 200)
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), width=0.8)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), width=0.8)
    for column, text in enumerate(("Variable", "Coef.", "SE", "z", "p")):
        page.insert_text((xs[column] + 4, 160), text, fontsize=9)
    for column, text in enumerate(("Treatment", "0.100", "0.050", "2.000", "0.046")):
        page.insert_text((xs[column] + 4, 190), text, fontsize=9)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_product_api_overview_search_runs_and_pwa(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_REPLICATION_AGENT", raising=False)
    client = TestClient(create_app(tmp_path))

    caps = client.get("/api/v1/capabilities")
    assert caps.status_code == 200
    assert caps.json()["api_version"] == "v1"
    assert caps.json()["features"]["command_palette"] is True
    assert caps.json()["replication"]["configured"] is False
    assert caps.json()["replication"]["permission_policy"] == "deny"
    assert caps.json()["replication"]["client_supplied_commands"] is False

    created = client.post(
        "/api/v1/audits",
        data={"title": "Product API paper"},
        files={"file": ("product.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    audit_id = created.json()["audit_id"]

    overview = client.get("/api/v1/overview").json()
    assert overview["audits_total"] == 1
    assert overview["papers_pages"] == 1
    assert overview["checks_total"] == 0

    search = client.get("/api/v1/search", params={"q": "Product API"}).json()
    assert any(item["kind"] == "audit" and item["audit_id"] == audit_id for item in search)

    stream = client.post(
        f"/api/v1/audits/{audit_id}/messages",
        json={"message": '/audit row="Treatment" table=2 page=1'},
    )
    assert stream.status_code == 200

    runs = client.get("/api/v1/runs").json()
    assert runs
    detector_run = next(
        run
        for run in runs
        if run["audit_id"] == audit_id and run["tool"] == "audit.regression"
    )
    assert detector_run["run_id"].startswith("run_")
    assert detector_run["run_kind"] == "detector"
    assert detector_run["phase"] == "finish"
    assert detector_run["duration_ms"] >= 0
    assert detector_run["artifact_id"].startswith("paper-")
    assert len(detector_run["parsers"]) >= 2

    detail_response = client.get(f'/api/v1/runs/{detector_run["run_id"]}')
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["run_id"] == detector_run["run_id"]
    assert detail["run_kind"] == "detector"
    assert detail["tool"] == "audit.regression"
    assert detail["artifact_id"] == detector_run["artifact_id"]
    assert detail["duration_ms"] >= 0
    assert detail["evidence"] is True
    assert [event["payload"]["phase"] for event in detail["events"] if event["kind"] == "tool"] == [
        "start",
        "finish",
    ]
    assert client.get("/api/v1/runs/run_missing").status_code == 404

    updated = client.get("/api/v1/overview").json()
    assert updated["checks_total"] > 0
    assert updated["checks_verified"] > 0

    replication = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={"prompt": "Reproduce the reported main result."},
    )
    assert replication.status_code == 503

    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert "Research Audit Workbench" in client.get("/").text


def test_replication_stream_is_correlated_and_server_configured(tmp_path, monkeypatch) -> None:
    class FakeRunner:
        def __init__(self, agent, *, permission_policy) -> None:
            self.agent = agent
            self.permission_policy = permission_policy

        async def stream_turn(self, workspace, prompt):
            assert workspace.name == "replication-workspace"
            assert (workspace / "paper.pdf").is_file()
            assert prompt == "Reproduce the reported main result."
            yield {
                "event_id": "rep_evt_test",
                "kind": "agent_update",
                "title": "plan",
                "detail": "Inspect the paper and reproduce the target result.",
                "status": "running",
                "payload": {"step": 1},
                "created_at": "2026-09-15T00:00:00Z",
            }

    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "fake-agent --stdio")
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT_NAME", "CI fake agent")
    monkeypatch.delenv("VERITAS_REPLICATION_PERMISSION_POLICY", raising=False)
    monkeypatch.setattr("veritas.harness.service.AcpTurnRunner", FakeRunner)

    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Replication paper"},
        files={"file": ("replication.pdf", _make_pdf(), "application/pdf")},
    ).json()
    audit_id = created["audit_id"]

    caps = client.get("/api/v1/capabilities").json()
    assert caps["replication"]["configured"] is True
    assert caps["replication"]["agent"] == "CI fake agent"
    assert caps["replication"]["permission_policy"] == "deny"

    prompt = "Reproduce the reported main result."
    response = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={"prompt": prompt},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [event["kind"] for event in events] == ["tool", "replication", "tool"]
    run_ids = {event["payload"]["run_id"] for event in events}
    assert len(run_ids) == 1
    run_id = run_ids.pop()
    assert run_id.startswith("run_")
    assert events[0]["payload"]["phase"] == "start"
    assert events[-1]["payload"]["phase"] == "finish"
    assert events[-1]["payload"]["duration_ms"] >= 0
    assert prompt not in json.dumps(events[0], ensure_ascii=False)

    runs = client.get("/api/v1/runs").json()
    replication_run = next(run for run in runs if run["run_id"] == run_id)
    assert replication_run["tool"] == "replication.acp"
    assert replication_run["run_kind"] == "replication"
    assert replication_run["phase"] == "finish"
    assert replication_run["evidence"] is False

    detail = client.get(f"/api/v1/runs/{run_id}").json()
    assert detail["run_kind"] == "replication"
    assert detail["tool"] == "replication.acp"
    assert detail["duration_ms"] >= 0
    assert detail["evidence"] is False
    assert [event["kind"] for event in detail["events"]] == ["tool", "replication", "tool"]


def test_empty_message_is_rejected(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Empty message paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    ).json()
    response = client.post(
        f'/api/v1/audits/{created["audit_id"]}/messages',
        json={"message": "   "},
    )
    assert response.status_code == 422

    replication = client.post(
        f'/api/v1/audits/{created["audit_id"]}/replication',
        json={"prompt": "   "},
    )
    assert replication.status_code == 422
