from __future__ import annotations

from veritas.harness.models import HarnessEvent
from veritas.harness.product_service import ProductAuditHarness as LegacyProductAuditHarness
from veritas.harness.product_service_runs import ProductAuditHarness


def _seed_audit(runtime: ProductAuditHarness, title: str, *, events: int = 6) -> str:
    record = runtime.store.create_audit(
        title=title,
        filename=f"{title}.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 10},
    )
    audit_id = str(record["audit_id"])
    for index in range(events):
        runtime.store.append_event(
            HarnessEvent(
                audit_id=audit_id,
                event_id=f"evt_{title}_{index}",
                kind="tool" if index % 2 else "paper",
                title=f"{title} activity {index}",
                detail=f"detail {index}",
                status="success",
                created_at=f"2026-10-01T00:00:{index:02d}Z",
            )
        )
    return audit_id


def _forbid_scan(*_args, **_kwargs):
    raise AssertionError("warm overview must not rescan authoritative event history")


def test_overview_cold_scan_then_warm_projection_without_rescan(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    for index in range(3):
        _seed_audit(runtime, f"Audit {index}")

    cold = runtime.overview()
    assert cold["audits_total"] == 3
    assert len(cold["recent_activity"]) == 8

    monkeypatch.setattr(runtime.store, "scan_events", _forbid_scan)
    warm = runtime.overview()

    assert warm == cold


def test_overview_projection_tracks_store_append_without_rescan(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Append", events=5)
    cold = runtime.overview()
    assert cold["recent_activity"][0]["title"] == "Append activity 4"

    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            event_id="evt_append_new",
            kind="tool",
            title="Append activity newest",
            detail="newest detail",
            status="success",
            created_at="2026-10-01T00:00:09Z",
        )
    )

    monkeypatch.setattr(runtime.store, "scan_events", _forbid_scan)
    warm = runtime.overview()

    assert warm["audits_total"] == 1
    assert warm["recent_activity"][0]["event_id"] == "evt_append_new"
    assert [item["title"] for item in warm["recent_activity"][:4]] == [
        "Append activity newest",
        "Append activity 4",
        "Append activity 3",
        "Append activity 2",
    ]


def test_overview_cached_tail_fails_closed_after_external_corruption(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Integrity", events=5)
    assert runtime.overview()["audits_total"] == 1

    journal = tmp_path / audit_id / "events.ndjson"
    with journal.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    overview = runtime.overview()
    assert overview["audits_total"] == 0
    assert overview["recent_activity"] == []


def test_overview_inline_audit_reparses_without_journal_watermark(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    record = runtime.store.create_audit(
        title="Legacy inline",
        filename="legacy-inline.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 10},
    )
    audit_id = str(record["audit_id"])
    assert not (tmp_path / audit_id / "events.ndjson").exists()

    original = runtime.store.scan_events
    scans: list[str] = []

    def tracked_scan(current_audit_id: str, visitor):
        scans.append(current_audit_id)
        return original(current_audit_id, visitor)

    monkeypatch.setattr(runtime.store, "scan_events", tracked_scan)
    assert runtime.overview()["audits_total"] == 1
    assert runtime.overview()["audits_total"] == 1
    assert scans == [audit_id, audit_id]


def test_overview_projection_preserves_legacy_product_semantics(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    first = _seed_audit(runtime, "First", events=6)
    _seed_audit(runtime, "Second", events=3)
    runtime.store.set_latest_result(
        first,
        {
            "verification_coverage": 0.75,
            "counts": {"verified": 3, "needs_review": 1, "contradictions": 1},
            "findings": [],
        },
    )

    indexed = runtime.overview()
    legacy = LegacyProductAuditHarness(tmp_path).overview()

    assert indexed == legacy
