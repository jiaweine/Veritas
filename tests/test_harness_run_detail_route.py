from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.models import HarnessEvent
from veritas.harness.product_service import ProductAuditHarness
from veritas.harness.service import AuditHarness
from veritas.harness.web import create_app


def _seed_run(runtime: AuditHarness, *, title: str = "Run detail") -> tuple[str, str]:
    record = runtime.store.create_audit(
        title=title,
        filename="paper.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 0},
    )
    audit_id = str(record["audit_id"])
    run_id = f"run_{audit_id}_detail"
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Detector started",
            detail="start",
            status="running",
            payload={
                "tool": "audit.regression",
                "run_kind": "detector",
                "run_id": run_id,
                "phase": "start",
                "artifact_id": "paper-test",
            },
        )
    )
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Detector finished",
            detail="finish",
            status="success",
            payload={
                "tool": "audit.regression",
                "run_kind": "detector",
                "run_id": run_id,
                "phase": "finish",
                "duration_ms": 7,
                "artifact_id": "paper-test",
                "result": {
                    "verification_coverage": 1.0,
                    "counts": {"verified": 1},
                    "source": {"page": 1},
                },
            },
        )
    )
    return audit_id, run_id


def test_run_detail_api_delegates_to_bounded_product_runtime(tmp_path, monkeypatch) -> None:
    seed = ProductAuditHarness(tmp_path)
    audit_id, run_id = _seed_run(seed)
    app = create_app(tmp_path)
    runtime = app.state.harness
    assert isinstance(runtime, ProductAuditHarness)

    def forbidden_list_audits() -> list[dict[str, object]]:
        raise AssertionError("run-detail API must not hydrate all audit histories")

    def forbidden_get_events(*_args, **_kwargs):
        raise AssertionError("run-detail API must use the streaming product scan")

    monkeypatch.setattr(runtime, "list_audits", forbidden_list_audits)
    monkeypatch.setattr(runtime.store, "get_events", forbidden_get_events)

    with TestClient(app) as client:
        response = client.get(f"/api/v1/runs/{run_id}")
        missing = client.get("/api/v1/runs/run_missing")

    assert response.status_code == 200
    detail = response.json()
    assert detail["run_id"] == run_id
    assert detail["audit_id"] == audit_id
    assert detail["tool"] == "audit.regression"
    assert detail["run_kind"] == "detector"
    assert detail["duration_ms"] == 7
    assert detail["evidence"] is True
    assert [event["payload"]["phase"] for event in detail["events"]] == ["start", "finish"]
    assert missing.status_code == 404


def test_run_detail_api_keeps_explicit_legacy_harness_compatible(tmp_path) -> None:
    data_dir = tmp_path / "legacy"
    runtime = AuditHarness(data_dir)
    audit_id, run_id = _seed_run(runtime, title="Legacy run detail")
    app = create_app(data_dir, harness=runtime)

    with TestClient(app) as client:
        response = client.get(f"/api/v1/runs/{run_id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["run_id"] == run_id
    assert detail["audit_id"] == audit_id
    assert detail["tool"] == "audit.regression"
    assert detail["events"][0]["payload"]["phase"] == "start"
    assert detail["events"][-1]["payload"]["phase"] == "finish"
