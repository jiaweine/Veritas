from __future__ import annotations

import json
from pathlib import Path

from veritas.harness.models import HarnessEvent
from veritas.harness.product_service import ProductAuditHarness
from veritas.harness.web import create_app


def _create_audit(runtime: ProductAuditHarness, title: str) -> str:
    record = runtime.store.create_audit(
        title=title,
        filename=f"{title}.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 10},
    )
    return str(record["audit_id"])


def _bulk_journal(runtime: ProductAuditHarness, audit_id: str, *, count: int) -> Path:
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="paper",
            title="Paper parsed",
            detail="seed",
            status="success",
            created_at="2026-09-30T00:00:00Z",
        )
    )
    journal = runtime.store.root / audit_id / "events.ndjson"
    with journal.open("a", encoding="utf-8", newline="\n") as handle:
        for index in range(count):
            phase = "finish" if index % 250 == 249 else "update"
            kind = "tool" if phase == "finish" else "replication"
            payload = (
                {
                    "tool": "replication.acp",
                    "run_kind": "replication",
                    "run_id": f"run_{audit_id}_{index}",
                    "phase": "finish",
                    "duration_ms": index,
                    "result": {
                        "status": "completed",
                        "verification_coverage": 0.0,
                        "counts": {},
                    },
                }
                if phase == "finish"
                else {
                    "tool": "replication.acp",
                    "run_kind": "replication",
                    "run_id": f"run_{audit_id}_stream",
                    "phase": "update",
                }
            )
            event = {
                "audit_id": audit_id,
                "event_id": f"evt_{audit_id}_{index}",
                "kind": kind,
                "title": "needle event" if index == count // 2 else f"event {index}",
                "detail": f"detail {index}",
                "status": "success" if phase == "finish" else "running",
                "payload": payload,
                "created_at": f"2026-09-30T00:{index // 60:02d}:{index % 60:02d}Z",
            }
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return journal


def test_default_web_runtime_uses_bounded_product_harness(tmp_path) -> None:
    app = create_app(tmp_path)
    assert isinstance(app.state.harness, ProductAuditHarness)


def test_product_views_do_not_full_hydrate_all_audits(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    first = _create_audit(runtime, "First")
    second = _create_audit(runtime, "Second")
    _bulk_journal(runtime, first, count=1000)
    _bulk_journal(runtime, second, count=1000)

    runtime.store.set_latest_result(
        first,
        {
            "verification_coverage": 0.75,
            "counts": {"verified": 3, "needs_review": 1, "contradictions": 1},
            "findings": [
                {
                    "title": "Synthetic contradiction",
                    "explanation": "Stress fixture",
                    "severity": "contradiction",
                }
            ],
        },
    )

    original = runtime.store.list_audits
    include_events_values: list[bool] = []

    def tracked_list_audits(*, include_events: bool = True, event_limit: int | None = None):
        include_events_values.append(include_events)
        return original(include_events=include_events, event_limit=event_limit)

    monkeypatch.setattr(runtime.store, "list_audits", tracked_list_audits)

    overview = runtime.overview()
    findings = runtime.findings()
    runs = runtime.runs()
    search = runtime.search("needle", limit=2)

    assert overview["audits_total"] == 2
    assert len(overview["recent_activity"]) == 8
    assert findings[0]["title"] == "Synthetic contradiction"
    assert len(runs) == 8
    assert len(search) == 2
    assert all(item["kind"] == "event" for item in search)
    assert include_events_values == [False, False, False, False]


def test_overview_retains_only_four_events_per_audit_for_activity(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_ids = [_create_audit(runtime, f"Audit {index}") for index in range(4)]
    for audit_id in audit_ids:
        _bulk_journal(runtime, audit_id, count=20)

    original = runtime.store.get_events
    limits: list[int | None] = []

    def tracked_get_events(audit_id: str, *, limit: int | None = None):
        limits.append(limit)
        return original(audit_id, limit=limit)

    monkeypatch.setattr(runtime.store, "get_events", tracked_get_events)
    result = runtime.overview()

    assert len(result["recent_activity"]) == 8
    assert limits[:2] == [4, 4]
    assert limits[2:] == [0, 0]


def test_corrupt_journal_is_omitted_from_product_views(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    good = _create_audit(runtime, "Good")
    bad = _create_audit(runtime, "Bad")
    _bulk_journal(runtime, good, count=4)
    bad_journal = _bulk_journal(runtime, bad, count=4)
    with bad_journal.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    overview = runtime.overview()
    search = runtime.search("event", limit=20)
    runs = runtime.runs()

    assert overview["audits_total"] == 1
    assert all(item["audit_id"] == good for item in search)
    assert all(item["audit_id"] == good for item in runs)
