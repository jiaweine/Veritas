from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from veritas.harness.models import HarnessEvent
from veritas.harness.product_service import ProductAuditHarness
from veritas.harness.replication_workspace_product import find_replication_audit
from veritas.harness.service import AuditHarness
from veritas.harness.web import create_app


def _seed_audit(runtime: AuditHarness, title: str = "Auxiliary read paper") -> str:
    record = runtime.store.create_audit(
        title=title,
        filename="paper.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 1},
    )
    audit_id = str(record["audit_id"])
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="paper",
            title="Paper parsed",
            detail="seed event",
            status="success",
        )
    )
    return audit_id


def _append_replication_terminal(runtime: AuditHarness, audit_id: str, run_id: str) -> None:
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Replication run completed",
            detail="done",
            status="success",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "finish",
                "duration_ms": 1,
                "result": {
                    "status": "completed",
                    "verification_coverage": 0.0,
                    "counts": {},
                },
            },
        )
    )


def _forbid_hydrated_reads(*_args, **_kwargs):
    raise AssertionError("auxiliary product routes must not hydrate audit event lists")


def test_project_and_intake_routes_use_bounded_audit_metadata(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime)
    app = create_app(tmp_path, harness=runtime)
    client = TestClient(app)

    original_store_list = runtime.store.list_audits
    include_events_values: list[bool] = []

    def tracked_store_list(*, include_events: bool = True, event_limit: int | None = None):
        include_events_values.append(include_events)
        return original_store_list(include_events=include_events, event_limit=event_limit)

    monkeypatch.setattr(runtime.store, "list_audits", tracked_store_list)
    monkeypatch.setattr(runtime.store, "get_events", _forbid_hydrated_reads)
    monkeypatch.setattr(runtime, "list_audits", _forbid_hydrated_reads)
    monkeypatch.setattr(runtime, "get_audit", _forbid_hydrated_reads)

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert projects.json()["unassigned_audit_ids"] == [audit_id]

    project = client.post("/api/v1/projects", json={"name": "Bounded reads"})
    assert project.status_code == 200
    project_id = project.json()["project_id"]

    assigned = client.post(
        f"/api/v1/audits/{audit_id}/project",
        json={"project_id": project_id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["project_id"] == project_id

    audit_project = client.get(f"/api/v1/audits/{audit_id}/project")
    assert audit_project.status_code == 200
    assert audit_project.json()["project_id"] == project_id

    attached = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={"file": ("data.txt", b"replication input", "text/plain")},
    )
    assert attached.status_code == 200

    unavailable_replication = client.post(
        f"/api/v1/audits/{audit_id}/replication",
        json={"prompt": "Reproduce the reported result."},
    )
    assert unavailable_replication.status_code == 503

    assert include_events_values
    assert all(value is False for value in include_events_values)


def test_product_audit_metadata_preserves_corrupt_journal_fail_closed(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime)
    journal = runtime.store.root / audit_id / "events.ndjson"
    with journal.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    assert runtime.audit_ids() == []
    with pytest.raises(ValueError):
        runtime.get_audit_metadata(audit_id)


def test_replication_owner_lookup_uses_bounded_run_projection(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime)
    run_id = "run_auxiliary_bounded"
    _append_replication_terminal(runtime, audit_id, run_id)

    monkeypatch.setattr(runtime.store, "get_events", _forbid_hydrated_reads)
    monkeypatch.setattr(runtime, "list_audits", _forbid_hydrated_reads)
    monkeypatch.setattr(runtime, "get_audit", _forbid_hydrated_reads)

    audit = find_replication_audit(runtime, run_id)
    assert audit["audit_id"] == audit_id
    assert audit.get("events") in (None, [])

    control = TestClient(create_app(tmp_path, harness=runtime)).get(
        f"/api/v1/replication/runs/{run_id}/control"
    )
    assert control.status_code == 200


def test_replication_owner_lookup_keeps_legacy_hydrated_fallback(tmp_path) -> None:
    runtime = AuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Legacy fallback")
    run_id = "run_auxiliary_legacy"
    _append_replication_terminal(runtime, audit_id, run_id)

    audit = find_replication_audit(runtime, run_id)
    assert audit["audit_id"] == audit_id
    assert any(event.get("payload", {}).get("run_id") == run_id for event in audit["events"])
