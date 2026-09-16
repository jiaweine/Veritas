from __future__ import annotations

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((30, 40), "Cache policy test", fontsize=12)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_api_and_evidence_responses_are_no_store(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.headers["cache-control"] == "no-store"

    created = client.post(
        "/api/v1/audits",
        data={"title": "Cache policy"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    assert created.headers["cache-control"] == "no-store"
    audit_id = created.json()["audit_id"]

    paper = client.get(f"/api/v1/audits/{audit_id}/paper")
    assert paper.status_code == 200
    assert paper.headers["cache-control"] == "no-store"

    attached = client.post(
        f"/api/v1/audits/{audit_id}/attachments",
        files={"file": ("analysis.py", b"print('ok')\n", "text/x-python")},
    )
    assert attached.status_code == 200
    assert attached.headers["cache-control"] == "no-store"
    attachment_id = attached.json()["attachment_id"]

    downloaded = client.get(f"/api/v1/audits/{audit_id}/attachments/{attachment_id}")
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "no-store"

    shell = client.get("/")
    assert shell.status_code == 200
    assert shell.headers.get("cache-control") != "no-store"
