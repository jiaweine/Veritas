from __future__ import annotations

import json

import pymupdf
from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 72), "Synthetic Social Science Article", fontsize=14)
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


def test_web_harness_upload_stream_and_pdf(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    assert client.get("/api/health").json()["status"] == "ok"
    assert "Research Audit Harness" in client.get("/").text

    created = client.post(
        "/api/audits",
        data={"title": "Synthetic paper"},
        files={"file": ("paper.pdf", _make_pdf(), "application/pdf")},
    )
    assert created.status_code == 200
    audit = created.json()
    audit_id = audit["audit_id"]

    paper = client.get(f"/api/audits/{audit_id}/paper")
    assert paper.status_code == 200
    assert paper.content.startswith(b"%PDF")

    response = client.post(
        f"/api/audits/{audit_id}/messages",
        json={"message": '/audit row="Treatment" table=2 page=1'},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert any(event["kind"] == "tool" for event in events)
    final_results = [
        event["payload"]["result"]
        for event in events
        if event.get("payload", {}).get("result")
    ]
    assert final_results
    assert final_results[-1]["status"] == "verified"
