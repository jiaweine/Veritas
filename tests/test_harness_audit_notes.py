from __future__ import annotations

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.store import MAX_AUDIT_NOTES_CHARS
from veritas.harness.web import create_app


def _paper_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Audit notes test paper", fontsize=14)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _create_audit(client: TestClient) -> str:
    response = client.post(
        "/api/v1/audits",
        data={"title": "Notes paper"},
        files={"file": ("notes.pdf", _paper_pdf(), "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()["audit_id"]


def test_audit_notes_are_persisted_and_reload_with_workspace(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    audit_id = _create_audit(client)

    created = client.get(f"/api/v1/audits/{audit_id}")
    assert created.status_code == 200
    assert created.json()["notes"] == ""
    assert created.json()["notes_updated_at"] is None

    content = "Check Table 4 wording before handoff.\nFollow up on the reported SE."
    saved = client.post(
        f"/api/v1/audits/{audit_id}/notes",
        json={"content": content},
    )
    assert saved.status_code == 200
    assert saved.headers["cache-control"] == "no-store"
    assert saved.json()["audit_id"] == audit_id
    assert saved.json()["notes"] == content
    assert saved.json()["notes_updated_at"]

    reloaded = TestClient(create_app(tmp_path)).get(f"/api/v1/audits/{audit_id}")
    assert reloaded.status_code == 200
    assert reloaded.json()["notes"] == content
    assert reloaded.json()["notes_updated_at"] == saved.json()["notes_updated_at"]

    cleared = client.post(
        f"/api/v1/audits/{audit_id}/notes",
        json={"content": ""},
    )
    assert cleared.status_code == 200
    assert cleared.json()["notes"] == ""
    assert client.get(f"/api/v1/audits/{audit_id}").json()["notes"] == ""


def test_audit_notes_fail_closed_on_invalid_targets_and_size(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    audit_id = _create_audit(client)

    baseline = "keep me"
    assert client.post(
        f"/api/v1/audits/{audit_id}/notes",
        json={"content": baseline},
    ).status_code == 200

    oversized = client.post(
        f"/api/v1/audits/{audit_id}/notes",
        json={"content": "x" * (MAX_AUDIT_NOTES_CHARS + 1)},
    )
    assert oversized.status_code == 422
    assert client.get(f"/api/v1/audits/{audit_id}").json()["notes"] == baseline

    missing = client.post(
        "/api/v1/audits/audit_missing/notes",
        json={"content": "note"},
    )
    assert missing.status_code == 404


def test_notes_revision_precondition_rejects_lost_updates(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    audit_id = _create_audit(client)
    url = f"/api/v1/audits/{audit_id}/notes"

    # Explicit null guards a document with no prior note revision.
    first = client.post(url, json={"content": "Review A", "expected_updated_at": None})
    assert first.status_code == 200
    version_a = first.json()["notes_updated_at"]
    assert version_a

    # Another tab working from the initial empty revision must not erase A.
    stale = client.post(url, json={"content": "Review B", "expected_updated_at": None})
    assert stale.status_code == 409
    assert "changed since" in stale.json()["detail"]
    assert client.get(f"/api/v1/audits/{audit_id}").json()["notes"] == "Review A"

    # A client presenting the actual persisted revision may update.
    second = client.post(url, json={"content": "Review A amended", "expected_updated_at": version_a})
    assert second.status_code == 200
    version_b = second.json()["notes_updated_at"]
    assert version_b
    assert second.json()["notes"] == "Review A amended"

    rejected = client.post(url, json={"content": "Stale A", "expected_updated_at": version_a})
    assert rejected.status_code == 409
    assert client.get(f"/api/v1/audits/{audit_id}").json()["notes"] == "Review A amended"

    # Existing API clients which omit the field remain backward compatible.
    legacy = client.post(url, json={"content": "Legacy save"})
    assert legacy.status_code == 200


def test_notes_revision_conflict_shared_between_store_instances(tmp_path) -> None:
    app_a = TestClient(create_app(tmp_path))
    app_b = TestClient(create_app(tmp_path))
    audit_id = _create_audit(app_a)
    url = f"/api/v1/audits/{audit_id}/notes"

    original = app_a.get(f"/api/v1/audits/{audit_id}").json()["notes_updated_at"]
    assert original is None
    assert app_a.post(url, json={"content": "A", "expected_updated_at": original}).status_code == 200
    assert app_b.post(url, json={"content": "B", "expected_updated_at": original}).status_code == 409
    assert app_a.get(f"/api/v1/audits/{audit_id}").json()["notes"] == "A"
