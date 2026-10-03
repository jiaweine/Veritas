from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.models import HarnessEvent
from veritas.harness.web import create_app


def _seed_finding_audit(runtime, count: int, *, title: str = "Finding audit") -> str:
    record = runtime.store.create_audit(
        title=title,
        filename="finding-paper.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": 8, "tables_detected": 2, "words": 2400},
    )
    audit_id = str(record["audit_id"])
    findings = [
        {
            "title": f"Finding {index:02d}",
            "explanation": f"Evidence-linked contradiction {index:02d}.",
            "severity": "contradiction" if index % 2 == 0 else "warning",
            "source": {"page": 3, "table": "Table 2", "row": f"Treatment {index:02d}"},
        }
        for index in range(count)
    ]
    runtime.store.set_latest_result(
        audit_id,
        {
            "status": "contradiction",
            "verification_coverage": 0.8,
            "source": {"page": 3, "table": "Table 2"},
            "counts": {"verified": 3, "needs_review": 0, "contradictions": count},
            "checks": [],
            "findings": findings,
        },
    )
    return audit_id


def test_finding_pages_are_bounded_keyset_latest_result_projections(tmp_path) -> None:
    app = create_app(tmp_path)
    runtime = app.state.harness
    audit_id = _seed_finding_audit(runtime, 60)

    client = TestClient(app)
    first = client.get("/api/v1/finding-pages", params={"limit": 50})
    assert first.status_code == 200
    payload = first.json()
    assert len(payload["items"]) == 50
    assert payload["total"] == 60
    assert payload["has_more"] is True
    assert payload["next_cursor"]
    assert payload["severity_counts"] == {"contradiction": 30, "warning": 30}
    assert [item["finding_id"] for item in payload["items"]] == [
        f"{audit_id}:finding:{index}" for index in range(50)
    ]

    second = client.get(
        "/api/v1/finding-pages",
        params={"limit": 50, "cursor": payload["next_cursor"]},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert len(second_payload["items"]) == 10
    assert second_payload["total"] == 60
    assert second_payload["has_more"] is False
    assert second_payload["next_cursor"] is None
    assert second_payload["severity_counts"] == payload["severity_counts"]
    assert [item["finding_id"] for item in second_payload["items"]] == [
        f"{audit_id}:finding:{index}" for index in range(50, 60)
    ]

    ids = [item["finding_id"] for item in payload["items"] + second_payload["items"]]
    assert len(ids) == len(set(ids)) == 60
    assert all(set(item) == {
        "finding_id",
        "audit_id",
        "audit_title",
        "title",
        "explanation",
        "severity",
        "source",
        "updated_at",
    } for item in payload["items"])


def test_finding_pages_fail_closed_on_corrupt_event_history(tmp_path) -> None:
    app = create_app(tmp_path)
    runtime = app.state.harness
    good_id = _seed_finding_audit(runtime, 1, title="Good finding")
    bad_id = _seed_finding_audit(runtime, 1, title="Bad finding")
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
    response = client.get("/api/v1/finding-pages", params={"limit": 50})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["audit_id"] for item in payload["items"]] == [good_id]
    assert bad_id not in {item["audit_id"] for item in payload["items"]}


def test_finding_page_rejects_invalid_cursor_and_preserves_legacy_route(tmp_path) -> None:
    app = create_app(tmp_path)
    runtime = app.state.harness
    audit_id = _seed_finding_audit(runtime, 3)
    client = TestClient(app)

    invalid = client.get("/api/v1/finding-pages", params={"cursor": "not-a-valid-cursor"})
    assert invalid.status_code == 422
    assert "finding cursor" in invalid.json()["detail"]

    legacy = client.get("/api/v1/findings")
    assert legacy.status_code == 200
    assert [item["finding_id"] for item in legacy.json()] == [
        f"{audit_id}:finding:{index}" for index in range(3)
    ]
