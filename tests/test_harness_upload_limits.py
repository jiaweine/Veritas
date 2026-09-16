from __future__ import annotations

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((30, 40), "Upload limit test", fontsize=12)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_pdf_upload_limit_rejects_before_harness_processing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("veritas.harness.web.MAX_UPLOAD_BYTES", 8)
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/v1/audits",
        data={"title": "Too large"},
        files={"file": ("paper.pdf", b"%PDF-1.7\n123456789", "application/pdf")},
    )

    assert response.status_code == 413
    assert "80 MiB" in response.json()["detail"]
    assert client.get("/api/v1/audits").json() == []


def test_attachment_upload_limit_rejects_without_mutating_manifest(tmp_path, monkeypatch) -> None:
    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/v1/audits",
        data={"title": "Attachment limit"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    audit_id = created.json()["audit_id"]

    monkeypatch.setattr("veritas.harness.web.MAX_ATTACHMENT_BYTES", 8)
    response = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={"file": ("large.csv", b"123456789", "text/csv")},
    )

    assert response.status_code == 413
    assert "80 MiB" in response.json()["detail"]
    assert client.get(f"/api/v1/audits/{audit_id}/attachments").json() == []
