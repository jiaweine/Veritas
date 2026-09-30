from __future__ import annotations

import json
import threading
from pathlib import Path

from veritas.harness.models import HarnessEvent
from veritas.harness.product_service import ProductAuditHarness
from veritas.harness.product_store import ProductHarnessStore
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


def test_default_web_runtime_uses_streaming_product_store(tmp_path) -> None:
    app = create_app(tmp_path)
    assert isinstance(app.state.harness, ProductAuditHarness)
    assert isinstance(app.state.harness.store, ProductHarnessStore)


def test_product_views_never_materialize_complete_event_lists(tmp_path, monkeypatch) -> None:
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

    def forbidden_get_events(*_args, **_kwargs):
        raise AssertionError("derived product views must use streaming scans")

    monkeypatch.setattr(runtime.store, "list_audits", tracked_list_audits)
    monkeypatch.setattr(runtime.store, "get_events", forbidden_get_events)

    overview = runtime.overview()
    findings = runtime.findings()
    runs = runtime.runs()
    search = runtime.search("needle", limit=2)
    detail = runtime.run_detail(f"run_{first}_249")

    assert overview["audits_total"] == 2
    assert len(overview["recent_activity"]) == 8
    assert findings[0]["title"] == "Synthetic contradiction"
    assert len(runs) == 8
    assert len(search) == 2
    assert all(item["kind"] == "event" for item in search)
    assert detail is not None
    assert detail["audit_id"] == first
    assert len(detail["events"]) == 1
    assert include_events_values == [False, False, False, False, False]


def test_streaming_scanner_visits_large_journal_in_order(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _create_audit(runtime, "Large")
    _bulk_journal(runtime, audit_id, count=5000)

    seen = 0
    first_event_id: str | None = None
    last_event_id: str | None = None

    def visitor(event: dict[str, object]) -> None:
        nonlocal seen, first_event_id, last_event_id
        event_id = str(event.get("event_id") or "")
        if first_event_id is None:
            first_event_id = event_id
        last_event_id = event_id
        seen += 1

    count = runtime.store.scan_events(audit_id, visitor)

    assert count == 5001
    assert seen == 5001
    assert first_event_id is not None and first_event_id.startswith("evt_")
    assert last_event_id == f"evt_{audit_id}_4999"


def test_streaming_scanner_releases_root_lock_before_visiting_snapshot(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _create_audit(runtime, "Concurrent")
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="paper",
            title="Seed event",
            detail="snapshot boundary",
        )
    )

    visitor_entered = threading.Event()
    release_visitor = threading.Event()
    append_done = threading.Event()
    seen: list[str] = []
    scan_errors: list[Exception] = []
    append_errors: list[Exception] = []

    def visitor(event: dict[str, object]) -> None:
        seen.append(str(event.get("title") or ""))
        visitor_entered.set()
        if not release_visitor.wait(timeout=5):
            raise TimeoutError("test visitor was not released")

    def scan() -> None:
        try:
            runtime.store.scan_events(audit_id, visitor)
        except Exception as exc:  # pragma: no cover - surfaced by assertion below
            scan_errors.append(exc)

    def append() -> None:
        try:
            runtime.store.append_event(
                HarnessEvent(
                    audit_id=audit_id,
                    kind="replication",
                    title="Concurrent append",
                    detail="must not wait for the dashboard visitor",
                )
            )
        except Exception as exc:  # pragma: no cover - surfaced by assertion below
            append_errors.append(exc)
        finally:
            append_done.set()

    scan_thread = threading.Thread(target=scan, daemon=True)
    scan_thread.start()
    assert visitor_entered.wait(timeout=2)

    append_thread = threading.Thread(target=append, daemon=True)
    append_thread.start()
    try:
        assert append_done.wait(timeout=2), "event append blocked behind product scan visitor"
    finally:
        release_visitor.set()

    scan_thread.join(timeout=2)
    append_thread.join(timeout=2)
    assert not scan_thread.is_alive()
    assert not append_thread.is_alive()
    assert scan_errors == []
    assert append_errors == []
    assert seen == ["Seed event"]
    assert [event["title"] for event in runtime.store.get_events(audit_id)] == [
        "Seed event",
        "Concurrent append",
    ]


def test_overview_scans_all_events_but_retains_only_activity_tail(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_ids = [_create_audit(runtime, f"Audit {index}") for index in range(4)]
    for audit_id in audit_ids:
        _bulk_journal(runtime, audit_id, count=20)

    original = runtime.store.scan_events
    scanned_counts: list[int] = []

    def tracked_scan(audit_id: str, visitor):
        count = original(audit_id, visitor)
        scanned_counts.append(count)
        return count

    monkeypatch.setattr(runtime.store, "scan_events", tracked_scan)
    result = runtime.overview()

    assert len(result["recent_activity"]) == 8
    assert scanned_counts == [21, 21, 21, 21]


def test_corrupt_journal_never_leaks_partial_derived_results(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    good = _create_audit(runtime, "Good")
    bad = _create_audit(runtime, "Bad")
    _bulk_journal(runtime, good, count=4)
    bad_journal = _bulk_journal(runtime, bad, count=4)
    with bad_journal.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    overview = runtime.overview()
    # "event" matches before the corrupt final line. No partial result from the
    # bad audit may escape merely because search found an early hit.
    search = runtime.search("event", limit=20)
    runs = runtime.runs()

    assert overview["audits_total"] == 1
    assert all(item["audit_id"] == good for item in search)
    assert all(item["audit_id"] == good for item in runs)
