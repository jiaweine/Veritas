from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.models import HarnessEvent
from veritas.harness.web import create_app


def _seed_audit(runtime, index: int) -> str:
    record = runtime.store.create_audit(
        title=f"Audit {index:02d}",
        filename=f"paper-{index:02d}.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": index + 1, "tables_detected": 2, "words": 1000 + index},
    )
    audit_id = str(record["audit_id"])
    if index < 5:
        runtime.store.set_status(audit_id, "error")
    elif index < 15:
        runtime.store.set_status(audit_id, "running")
    return audit_id


def test_audit_pages_are_bounded_keyset_metadata_projections(tmp_path) -> None:
    app = create_app(tmp_path)
    runtime = app.state.harness
    for index in range(60):
        _seed_audit(runtime, index)

    client = TestClient(app)
    first = client.get("/api/v1/audit-pages", params={"limit": 50})
    assert first.status_code == 200
    payload = first.json()
    assert len(payload["items"]) == 50
    assert payload["total"] == 60
    assert payload["has_more"] is True
    assert payload["next_cursor"]
    assert payload["status_counts"] == {"ready": 45, "running": 10, "error": 5}
    assert all("events" not in item for item in payload["items"])
    assert all("notes" not in item for item in payload["items"])
    assert all("attachments" not in item for item in payload["items"])

    second = client.get(
        "/api/v1/audit-pages",
        params={"limit": 50, "cursor": payload["next_cursor"]},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert len(second_payload["items"]) == 10
    assert second_payload["total"] == 60
    assert second_payload["has_more"] is False
    assert second_payload["next_cursor"] is None
    assert second_payload["status_counts"] == payload["status_counts"]

    ids = [item["audit_id"] for item in payload["items"] + second_payload["items"]]
    assert len(ids) == 60
    assert len(set(ids)) == 60


def test_audit_pages_fail_closed_on_corrupt_event_history(tmp_path) -> None:
    app = create_app(tmp_path)
    runtime = app.state.harness
    good_id = _seed_audit(runtime, 20)
    bad_id = _seed_audit(runtime, 21)
    runtime.store.append_event(
        HarnessEvent(
            audit_id=bad_id,
            kind="paper",
            title="Corrupt me after a valid append",
            status="success",
        )
    )
    journal = tmp_path / bad_id / "events.ndjson"
    with journal.open("ab") as handle:
        handle.write(b"{not-json}\n")

    client = TestClient(app)
    response = client.get("/api/v1/audit-pages", params={"limit": 50})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["audit_id"] for item in payload["items"]] == [good_id]
    assert bad_id not in {item["audit_id"] for item in payload["items"]}


def test_audit_page_rejects_invalid_cursor_and_preserves_legacy_route(tmp_path) -> None:
    app = create_app(tmp_path)
    runtime = app.state.harness
    _seed_audit(runtime, 30)
    client = TestClient(app)

    invalid = client.get("/api/v1/audit-pages", params={"cursor": "not-a-valid-cursor"})
    assert invalid.status_code == 422
    assert "audit cursor" in invalid.json()["detail"]

    legacy = client.get("/api/v1/audits")
    assert legacy.status_code == 200
    assert len(legacy.json()) == 1
