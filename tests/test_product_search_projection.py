from __future__ import annotations

import json

from veritas.harness import product_store_runs
from veritas.harness.models import HarnessEvent
from veritas.harness.product_service import ProductAuditHarness as LegacyProductAuditHarness
from veritas.harness.product_service_runs import ProductAuditHarness


def _seed_audit(runtime: ProductAuditHarness, title: str, *, marker: str = "needle") -> str:
    record = runtime.store.create_audit(
        title=title,
        filename=f"{title}.pdf",
        pdf_bytes=b"%PDF-1.4\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 10},
    )
    audit_id = str(record["audit_id"])
    for index in range(5):
        runtime.store.append_event(
            HarnessEvent(
                audit_id=audit_id,
                event_id=f"evt_{title}_{index}",
                kind="tool" if index % 2 else "paper",
                title=f"{title} activity {index}",
                detail=(
                    f"detail {index} with {marker} AlphaBeta"
                    if index == 3
                    else f"detail {index}"
                ),
                status="success",
                created_at=f"2026-10-01T00:00:{index:02d}Z",
            )
        )
    return audit_id


def _append_external_event(tmp_path, audit_id: str, *, marker: str, index: int = 9) -> str:
    event_id = f"evt_external_{index}"
    event = {
        "audit_id": audit_id,
        "event_id": event_id,
        "kind": "paper",
        "title": "Externally appended authoritative activity",
        "detail": f"external detail with {marker}",
        "status": "success",
        "created_at": f"2026-10-01T00:00:{index:02d}Z",
    }
    journal = tmp_path / audit_id / "events.ndjson"
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event_id


def _forbid_scan(*_args, **_kwargs):
    raise AssertionError("warm search must not rescan authoritative event history")


def test_search_cold_scan_then_warm_queries_without_rescan(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    for index in range(3):
        _seed_audit(runtime, f"Audit {index}", marker="warm-needle")

    cold = runtime.search("arm-need", limit=20)
    assert len(cold) == 3
    assert all(item["kind"] == "event" for item in cold)

    monkeypatch.setattr(runtime.store, "scan_events", _forbid_scan)
    assert runtime.search("arm-need", limit=20) == cold
    assert len(runtime.search("lphab", limit=20)) == 3


def test_search_projection_tracks_store_append_without_rescan(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Append", marker="seed-marker")
    assert runtime.search("seed-marker", limit=20)

    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            event_id="evt_append_search_new",
            kind="paper",
            title="Fresh projected search event",
            detail="contains StoreManagedSubstringXYZ for immediate discovery",
            status="success",
            created_at="2026-10-01T00:00:09Z",
        )
    )

    monkeypatch.setattr(runtime.store, "scan_events", _forbid_scan)
    results = runtime.search("managedsubstringx", limit=20)

    assert results == [
        {
            "kind": "event",
            "id": "evt_append_search_new",
            "audit_id": audit_id,
            "title": "Fresh projected search event",
            "detail": "contains StoreManagedSubstringXYZ for immediate discovery",
            "status": "success",
        }
    ]


def test_external_revalidation_cannot_make_stale_search_projection_current(
    tmp_path, monkeypatch
) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Revalidated Search", marker="old-marker")
    assert runtime.search("old-marker", limit=20)

    event_id = _append_external_event(
        tmp_path,
        audit_id,
        marker="ExternalFreshSubstringXYZ",
    )
    runtime.store.validate_events(audit_id)

    original = runtime.store.scan_events
    scans: list[str] = []

    def tracked_scan(current_audit_id: str, visitor):
        scans.append(current_audit_id)
        return original(current_audit_id, visitor)

    monkeypatch.setattr(runtime.store, "scan_events", tracked_scan)
    results = runtime.search("freshsubstringx", limit=20)

    assert [item["id"] for item in results if item["kind"] == "event"] == [event_id]
    assert scans == [audit_id]


def test_external_revalidation_cannot_make_stale_overview_tail_current(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Revalidated Overview", marker="overview-marker")
    before = runtime.overview()
    assert before["recent_activity"][0]["audit_id"] == audit_id

    event_id = _append_external_event(
        tmp_path,
        audit_id,
        marker="overview-external-marker",
    )
    runtime.store.validate_events(audit_id)

    after = runtime.overview()
    assert after["recent_activity"][0]["event_id"] == event_id


def test_search_cached_projection_fails_closed_after_external_corruption(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Integrity Search", marker="integrity-marker")
    assert runtime.search("integrity-marker", limit=20)

    journal = tmp_path / audit_id / "events.ndjson"
    with journal.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    # Neither cached event text nor matching audit metadata may escape once the
    # authoritative journal fingerprint changes and full validation fails.
    assert runtime.search("integrity", limit=20) == []


def test_search_inline_audit_reparses_without_journal_watermark(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    record = runtime.store.create_audit(
        title="Legacy inline searchable",
        filename="legacy-inline-searchable.pdf",
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
    assert runtime.search("inline searchable", limit=20)[0]["audit_id"] == audit_id
    assert runtime.search("inline searchable", limit=20)[0]["audit_id"] == audit_id
    assert scans == [audit_id, audit_id]


def test_oversized_search_projection_streams_without_becoming_resident(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(product_store_runs, "_SEARCH_CACHE_MAX_AUDIT_EVENTS", 3)
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Oversized", marker="oversized-marker")
    legacy = LegacyProductAuditHarness(tmp_path)

    original = runtime.store.scan_events
    scans: list[str] = []

    def tracked_scan(current_audit_id: str, visitor):
        scans.append(current_audit_id)
        return original(current_audit_id, visitor)

    monkeypatch.setattr(runtime.store, "scan_events", tracked_scan)
    expected = legacy.search("oversized-marker", limit=20)
    assert runtime.search("oversized-marker", limit=20) == expected
    assert runtime.search("oversized-marker", limit=20) == expected
    assert scans == [audit_id, audit_id]
    assert audit_id not in runtime.store._search_documents


def test_search_lru_respects_global_event_bound(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(product_store_runs, "_SEARCH_CACHE_MAX_EVENTS", 5)
    runtime = ProductAuditHarness(tmp_path)
    _seed_audit(runtime, "First bounded", marker="shared-bounded-marker")
    _seed_audit(runtime, "Second bounded", marker="shared-bounded-marker")

    results = runtime.search("shared-bounded-marker", limit=20)

    assert len([item for item in results if item["kind"] == "event"]) == 2
    assert runtime.store._search_cached_events <= 5
    assert len(runtime.store._search_documents) <= 1


def test_search_projection_preserves_legacy_substring_semantics_and_order(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    first_id = _seed_audit(runtime, "Alpha Search", marker="CaféCaseFold-Ωmega")
    _seed_audit(runtime, "Second Search", marker="prefix-AlphaBeta-suffix")

    legacy = LegacyProductAuditHarness(tmp_path)
    probes = (
        ("a", 1),
        ("al", 2),
        ("alpha", 1),
        ("alpha", 3),
        ("phabe", 20),
        ("cafécase", 20),
        ("ωmega", 20),
        ("search.pdf", 20),
        (first_id[-8:], 20),
        ("not-present", 20),
        ("alpha", 0),
        ("alpha", -1),
        ("   ", 20),
    )
    for query, limit in probes:
        assert runtime.search(query, limit=limit) == legacy.search(query, limit=limit)
