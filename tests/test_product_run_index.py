from __future__ import annotations

import json

import pytest

from veritas.harness.models import HarnessEvent
from veritas.harness.product_service import ProductAuditHarness


def _seed_audit(runtime: ProductAuditHarness, title: str) -> str:
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
            detail="seed",
            status="success",
        )
    )
    return audit_id


def _append_replication_run(
    runtime: ProductAuditHarness,
    audit_id: str,
    run_id: str,
) -> None:
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="replication",
            title="Replication update",
            detail="agent is working",
            status="running",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "update",
                "agent_event": {"kind": "message", "detail": "working"},
            },
        )
    )
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="replication_context",
            title="Scientific finding linked to replication",
            detail="binding only",
            status="info",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "context",
                "origin_finding": {
                    "finding_id": f"{audit_id}:finding:0",
                    "title": "Synthetic finding",
                    "severity": "contradiction",
                    "source": {"page": 1},
                    "binding_only": True,
                },
            },
        )
    )
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Replication run completed",
            detail="done",
            status="success",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "finish",
                "duration_ms": 5,
                "result": {
                    "status": "completed",
                    "verification_coverage": 0.0,
                    "counts": {},
                },
            },
        )
    )


def _forbid_scan(*_args, **_kwargs):
    raise AssertionError("warm indexed lookup must not rescan the authoritative journal")


def test_warm_run_detail_uses_validated_range_without_rescanning(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    _seed_audit(runtime, "Unrelated")
    target = _seed_audit(runtime, "Target")
    run_id = "run_indexed_warm"
    _append_replication_run(runtime, target, run_id)

    runtime.store.validate_events(target)
    first = runtime.run_detail(run_id)
    assert first is not None
    assert first["audit_id"] == target
    assert first["run_kind"] == "replication"
    assert first["origin_finding"]["finding_id"] == f"{target}:finding:0"

    monkeypatch.setattr(runtime.store, "scan_events", _forbid_scan)
    second = runtime.run_detail(run_id)
    assert second is not None
    assert second["run_id"] == run_id
    assert second["audit_id"] == target


def test_persisted_run_locator_skips_unrelated_audits_after_restart(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    unrelated = _seed_audit(runtime, "Large unrelated")
    for index in range(40):
        runtime.store.append_event(
            HarnessEvent(
                audit_id=unrelated,
                kind="paper",
                title=f"noise {index}",
                detail="not part of the target run",
            )
        )
    target = _seed_audit(runtime, "Indexed target")
    run_id = "run_indexed_restart"
    _append_replication_run(runtime, target, run_id)

    index_path = tmp_path / ".run-index.ndjson"
    assert index_path.is_file()
    assert run_id in index_path.read_text(encoding="utf-8")

    reloaded = ProductAuditHarness(tmp_path)
    original_scan = reloaded.store.scan_events
    scanned: list[str] = []

    def tracked_scan(audit_id: str, visitor):
        scanned.append(audit_id)
        return original_scan(audit_id, visitor)

    monkeypatch.setattr(reloaded.store, "scan_events", tracked_scan)
    detail = reloaded.run_detail(run_id)

    assert detail is not None
    assert detail["audit_id"] == target
    assert scanned == [target]


def test_forged_run_locator_cannot_rebind_run_to_another_audit(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    wrong = _seed_audit(runtime, "Wrong owner")
    target = _seed_audit(runtime, "Real owner")
    run_id = "run_indexed_forged"
    _append_replication_run(runtime, target, run_id)

    wrong_journal = tmp_path / wrong / "events.ndjson"
    forged = {
        "schema_version": "1",
        "run_id": run_id,
        "audit_id": wrong,
        "start": 0,
        "end": wrong_journal.stat().st_size,
        "complete": True,
    }
    with (tmp_path / ".run-index.ndjson").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(forged, sort_keys=True, separators=(",", ":")) + "\n")

    reloaded = ProductAuditHarness(tmp_path)
    detail = reloaded.run_detail(run_id)

    assert detail is not None
    assert detail["audit_id"] == target
    assert detail["tool"] == "replication.acp"


def test_corrupt_auxiliary_index_falls_back_to_authoritative_journals(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    target = _seed_audit(runtime, "Corrupt cache")
    run_id = "run_indexed_corrupt_cache"
    _append_replication_run(runtime, target, run_id)
    (tmp_path / ".run-index.ndjson").write_text("{not-json}\n", encoding="utf-8")

    reloaded = ProductAuditHarness(tmp_path)
    detail = reloaded.run_detail(run_id)

    assert detail is not None
    assert detail["audit_id"] == target


def test_journal_change_invalidates_warm_watermark_and_fails_closed(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    target = _seed_audit(runtime, "Journal integrity")
    run_id = "run_indexed_integrity"
    _append_replication_run(runtime, target, run_id)

    assert runtime.run_detail(run_id) is not None
    journal = tmp_path / target / "events.ndjson"
    with journal.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    assert runtime.run_detail(run_id) is None
    with pytest.raises(ValueError):
        runtime.store.validate_events(target)


def test_metadata_validation_watermark_avoids_repeat_noop_scans(tmp_path, monkeypatch) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime, "Validation watermark")
    runtime.store.validate_events(audit_id)

    monkeypatch.setattr(runtime.store, "scan_events", _forbid_scan)
    assert runtime.audit_ids() == [audit_id]
    assert runtime.get_audit_metadata(audit_id)["audit_id"] == audit_id
    assert runtime.findings() == []
