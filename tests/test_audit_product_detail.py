from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from veritas.harness.models import HarnessEvent
from veritas.harness.store import HarnessStore
from veritas.harness.web import create_app


ROOT = Path(__file__).resolve().parents[1]


def _seed_long_audit(tmp_path: Path, *, events: int = 40) -> str:
    store = HarnessStore(tmp_path)
    record = store.create_audit(
        title="Long conversation",
        filename="paper.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 0},
    )
    audit_id = str(record["audit_id"])
    for index in range(events):
        store.append_event(
            HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title=f"event-{index:03d}",
                status="info",
            )
        )
    return audit_id


def test_product_detail_returns_only_requested_authoritative_event_tail(tmp_path: Path) -> None:
    audit_id = _seed_long_audit(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get(f"/api/v1/audits/{audit_id}/product-detail?event_limit=7")
    assert response.status_code == 200
    bounded = response.json()
    assert [event["title"] for event in bounded["events"]] == [
        f"event-{index:03d}" for index in range(33, 40)
    ]

    legacy = client.get(f"/api/v1/audits/{audit_id}")
    assert legacy.status_code == 200
    assert len(legacy.json()["events"]) == 40


def test_product_detail_rejects_unbounded_or_invalid_limits(tmp_path: Path) -> None:
    audit_id = _seed_long_audit(tmp_path, events=2)
    client = TestClient(create_app(tmp_path))
    assert client.get(f"/api/v1/audits/{audit_id}/product-detail?event_limit=0").status_code == 422
    assert client.get(f"/api/v1/audits/{audit_id}/product-detail?event_limit=201").status_code == 422


def test_web_and_mobile_use_bounded_product_detail_contract() -> None:
    app = (ROOT / "src/veritas/harness/static/app.js").read_text(encoding="utf-8")
    mobile = (ROOT / "mobile/App.tsx").read_text(encoding="utf-8")
    service = (ROOT / "src/veritas/harness/service.py").read_text(encoding="utf-8")

    assert "const PRODUCT_AUDIT_EVENT_LIMIT = 24;" in app
    assert "product-detail?event_limit=${PRODUCT_AUDIT_EVENT_LIMIT}" in app
    assert "const PRODUCT_AUDIT_EVENT_LIMIT = 24;" in mobile
    assert "product-detail?event_limit=${PRODUCT_AUDIT_EVENT_LIMIT}" in mobile
    assert "record = self.store.get_audit(audit_id, event_limit=0)" in service
