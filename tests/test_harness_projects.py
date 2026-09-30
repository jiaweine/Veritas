from __future__ import annotations

import json

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.projects import MAX_PROJECT_NAME_CHARS
from veritas.harness.web import create_app


def _paper_pdf(label: str = "Project grouping test paper") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), label, fontsize=14)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _create_audit(client: TestClient, title: str = "Project paper") -> str:
    response = client.post(
        "/api/v1/audits",
        data={"title": title},
        files={"file": ("project.pdf", _paper_pdf(title), "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()["audit_id"]


def test_projects_persist_without_mutating_audit_evidence_records(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    empty = client.get("/api/v1/projects")
    assert empty.status_code == 200
    assert empty.headers["cache-control"] == "no-store"
    assert empty.json() == {
        "schema_version": "1",
        "projects": [],
        "assignments": {},
        "unassigned_audit_ids": [],
    }

    audit_id = _create_audit(client)
    unassigned = client.get("/api/v1/projects").json()
    assert unassigned["unassigned_audit_ids"] == [audit_id]

    created = client.post(
        "/api/v1/projects",
        json={"name": "  Minimum   wage   literature  "},
    )
    assert created.status_code == 200
    project = created.json()
    assert project["project_id"].startswith("project_")
    assert project["name"] == "Minimum wage literature"

    assigned = client.post(
        f"/api/v1/audits/{audit_id}/project",
        json={"project_id": project["project_id"]},
    )
    assert assigned.status_code == 200
    assert assigned.json()["project"] == project

    audit_project = client.get(f"/api/v1/audits/{audit_id}/project")
    assert audit_project.status_code == 200
    assert audit_project.json()["project_id"] == project["project_id"]

    snapshot = client.get("/api/v1/projects").json()
    assert snapshot["assignments"] == {audit_id: project["project_id"]}
    assert snapshot["unassigned_audit_ids"] == []
    assert snapshot["projects"][0]["audit_count"] == 1
    assert snapshot["projects"][0]["audit_ids"] == [audit_id]

    audit = client.get(f"/api/v1/audits/{audit_id}").json()
    assert "project_id" not in audit
    persisted_audit = json.loads((tmp_path / audit_id / "audit.json").read_text(encoding="utf-8"))
    assert "project_id" not in persisted_audit
    assert (tmp_path / "projects.json").is_file()

    reloaded = TestClient(create_app(tmp_path))
    persisted = reloaded.get("/api/v1/projects").json()
    assert persisted["assignments"] == {audit_id: project["project_id"]}
    assert persisted["projects"][0]["audit_count"] == 1

    cleared = reloaded.post(
        f"/api/v1/audits/{audit_id}/project",
        json={"project_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.json() == {"audit_id": audit_id, "project_id": None, "project": None}
    cleared_snapshot = reloaded.get("/api/v1/projects").json()
    assert cleared_snapshot["assignments"] == {}
    assert cleared_snapshot["unassigned_audit_ids"] == [audit_id]


def test_projects_validate_names_targets_and_duplicate_identity(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    audit_id = _create_audit(client)

    created = client.post("/api/v1/projects", json={"name": "Replication study"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    duplicate = client.post("/api/v1/projects", json={"name": " replication   STUDY "})
    assert duplicate.status_code == 422
    assert "already exists" in duplicate.json()["detail"]

    too_long = client.post(
        "/api/v1/projects",
        json={"name": "x" * (MAX_PROJECT_NAME_CHARS + 1)},
    )
    assert too_long.status_code == 422

    missing_project = client.post(
        f"/api/v1/audits/{audit_id}/project",
        json={"project_id": "project_missing"},
    )
    assert missing_project.status_code == 404

    malformed_project = client.post(
        f"/api/v1/audits/{audit_id}/project",
        json={"project_id": "../escape"},
    )
    assert malformed_project.status_code == 422

    missing_audit = client.post(
        "/api/v1/audits/audit_missing/project",
        json={"project_id": project_id},
    )
    assert missing_audit.status_code == 404


def test_project_metadata_corruption_fails_closed(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    audit_id = _create_audit(client)
    project = client.post("/api/v1/projects", json={"name": "Integrity"}).json()
    assert client.post(
        f"/api/v1/audits/{audit_id}/project",
        json={"project_id": project["project_id"]},
    ).status_code == 200

    (tmp_path / "projects.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "projects": [],
                "assignments": {audit_id: project["project_id"]},
            }
        ),
        encoding="utf-8",
    )

    failed = client.get("/api/v1/projects")
    assert failed.status_code == 500
    assert "project metadata integrity error" in failed.json()["detail"]

    create_failed = client.post("/api/v1/projects", json={"name": "Must not reset"})
    assert create_failed.status_code == 500
