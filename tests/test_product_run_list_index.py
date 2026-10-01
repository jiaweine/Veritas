from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from veritas.harness.models import HarnessEvent
from veritas.harness.product_service_runs import ProductAuditHarness
from veritas.harness.service import AuditHarness
from veritas.harness.web import create_app


def _seed_audit(runtime: ProductAuditHarness | AuditHarness, title: str = "Runs") -> str:
    record = runtime.store.create_audit(
        title=title,
        filename=f"{title}.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 1},
    )
    audit_id = str(record["audit_id"])
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="paper",
            title="Paper parsed",
            status="success",
            created_at="2026-01-01T00:00:00Z",
        )
    )
    return audit_id


def _terminal_event(audit_id: str, index: int) -> HarnessEvent:
    return HarnessEvent(
        audit_id=audit_id,
        kind="tool",
        title=f"Run {index}",
        detail="done",
        status="success",
        event_id=f"evt_run_{index:06d}",
        created_at=f"2026-01-01T00:00:00.{index:06d}Z",
        payload={
            "tool": "replication.acp",
            "run_kind": "replication",
            "run_id": f"run_{index:06d}",
            "phase": "finish",
            "duration_ms": index,
            "artifact_id": "paper-test",
            "result": {
                "status": "completed",
                "verification_coverage": index / 1000,
                "counts": {"verified": index % 3},
            },
        },
    )


def _forbid_scan(*_args, **_kwargs):
    raise AssertionError("warm run pages must not rescan authoritative event history")


def test_runs_page_uses_stable_keyset_cursor_without_warm_rescan(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime)
    for index in range(8):
        runtime.store.append_event(_terminal_event(audit_id, index))

    first = runtime.runs_page(limit=3)
    assert [item["run_id"] for item in first["items"]] == [
        "run_000007",
        "run_000006",
        "run_000005",
    ]
    assert first["has_more"] is True
    assert first["next_cursor"]

    monkeypatch.setattr(runtime.store, "scan_events", _forbid_scan)
    second = runtime.runs_page(limit=3, cursor=first["next_cursor"])
    third = runtime.runs_page(limit=3, cursor=second["next_cursor"])

    combined = first["items"] + second["items"] + third["items"]
    assert [item["run_id"] for item in combined] == [
        f"run_{index:06d}" for index in reversed(range(8))
    ]
    assert len({item["run_id"] for item in combined}) == 8
    assert third["has_more"] is False
    assert third["next_cursor"] is None


def test_runs_full_list_reuses_validated_terminal_projection(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Compatibility")
    for index in range(12):
        runtime.store.append_event(_terminal_event(audit_id, index))

    assert len(runtime.runs()) == 12
    monkeypatch.setattr(runtime.store, "scan_events", _forbid_scan)
    rows = runtime.runs()
    assert len(rows) == 12
    assert rows[0]["run_id"] == "run_000011"
    assert all(item["audit_title"] == "Compatibility" for item in rows)


@pytest.mark.parametrize(
    "cursor",
    ["%%%", "e30", "eyJ2IjoyLCJjcmVhdGVkX2F0IjoiIiwicnVuX2lkIjoieCJ9"],
)
def test_runs_page_rejects_malformed_or_unsupported_cursor(tmp_path, cursor) -> None:
    runtime = ProductAuditHarness(tmp_path)
    with pytest.raises(ValueError):
        runtime.runs_page(limit=10, cursor=cursor)


def test_corrupt_journal_cannot_leak_stale_run_projection(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Integrity")
    runtime.store.append_event(_terminal_event(audit_id, 1))
    assert runtime.runs_page(limit=10)["items"]

    journal = tmp_path / audit_id / "events.ndjson"
    with journal.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    assert runtime.runs_page(limit=10)["items"] == []
    with pytest.raises(ValueError):
        runtime.store.validate_events(audit_id)


def test_ten_thousand_run_cold_scan_then_bounded_warm_pages(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Ten thousand")
    journal = tmp_path / audit_id / "events.ndjson"

    with journal.open("a", encoding="utf-8") as handle:
        for index in range(10_000):
            handle.write(
                json.dumps(
                    _terminal_event(audit_id, index).to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

    reloaded = ProductAuditHarness(tmp_path)
    monkeypatch.setattr(
        reloaded.store,
        "get_events",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("run paging must not materialize full event lists")
        ),
    )
    first = reloaded.runs_page(limit=100)
    assert len(first["items"]) == 100
    assert first["items"][0]["run_id"] == "run_009999"
    assert first["items"][-1]["run_id"] == "run_009900"
    assert first["has_more"] is True

    monkeypatch.setattr(reloaded.store, "scan_events", _forbid_scan)
    second = reloaded.runs_page(limit=100, cursor=first["next_cursor"])
    assert len(second["items"]) == 100
    assert second["items"][0]["run_id"] == "run_009899"
    assert {item["run_id"] for item in first["items"]}.isdisjoint(
        item["run_id"] for item in second["items"]
    )


def test_default_web_app_exposes_bounded_run_pages(tmp_path) -> None:
    app = create_app(tmp_path)
    runtime = app.state.harness
    assert isinstance(runtime, ProductAuditHarness)
    audit_id = _seed_audit(runtime, "Web")
    for index in range(5):
        runtime.store.append_event(_terminal_event(audit_id, index))

    client = TestClient(app)
    first = client.get("/api/v1/run-pages", params={"limit": 2})
    assert first.status_code == 200
    page = first.json()
    assert [item["run_id"] for item in page["items"]] == ["run_000004", "run_000003"]
    assert page["has_more"] is True

    second = client.get(
        "/api/v1/run-pages",
        params={"limit": 2, "cursor": page["next_cursor"]},
    )
    assert second.status_code == 200
    assert [item["run_id"] for item in second.json()["items"]] == [
        "run_000002",
        "run_000001",
    ]

    bad = client.get("/api/v1/run-pages", params={"cursor": "%%%"})
    assert bad.status_code == 422


def test_custom_legacy_harness_keeps_paginated_route_compatibility(tmp_path) -> None:
    runtime = AuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Legacy")
    for index in range(4):
        runtime.store.append_event(_terminal_event(audit_id, index))
    client = TestClient(create_app(tmp_path, harness=runtime))

    first = client.get("/api/v1/run-pages", params={"limit": 2})
    assert first.status_code == 200
    assert first.json()["next_cursor"] == "2"
    second = client.get("/api/v1/run-pages", params={"limit": 2, "cursor": "2"})
    assert second.status_code == 200
    assert second.json()["has_more"] is False
