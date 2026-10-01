from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from veritas.harness import product_store as base_store
from veritas.harness import product_store_compact as compact_store
from veritas.harness.models import HarnessEvent
from veritas.harness.product_service import ProductAuditHarness


def _seed_audit(runtime: ProductAuditHarness, title: str = "Compaction paper") -> str:
    record = runtime.store.create_audit(
        title=title,
        filename="paper.pdf",
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


def _append_update(runtime: ProductAuditHarness, audit_id: str, run_id: str) -> None:
    runtime.store.append_event(
        HarnessEvent(
            audit_id=audit_id,
            kind="replication",
            title="Replication update",
            detail="working",
            status="running",
            payload={
                "tool": "replication.acp",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "update",
            },
        )
    )


def _append_terminal(runtime: ProductAuditHarness, audit_id: str, run_id: str) -> None:
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
                "duration_ms": 1,
                "result": {
                    "status": "completed",
                    "verification_coverage": 0.0,
                    "counts": {},
                },
            },
        )
    )


def _index_lines(path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_explicit_compaction_collapses_duplicate_run_records_and_survives_restart(
    tmp_path,
) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime)
    run_id = "run_compact_restart"
    _append_update(runtime, audit_id, run_id)
    _append_terminal(runtime, audit_id, run_id)

    index_path = tmp_path / ".run-index.ndjson"
    assert len(_index_lines(index_path)) >= 2

    assert runtime.store.compact_run_index() is True
    compacted = _index_lines(index_path)
    assert len(compacted) == 1
    assert compacted[0]["run_id"] == run_id
    assert compacted[0]["audit_id"] == audit_id
    assert compacted[0]["complete"] is True

    reloaded = ProductAuditHarness(tmp_path)
    detail = reloaded.run_detail(run_id)
    assert detail is not None
    assert detail["audit_id"] == audit_id
    assert detail["status"] == "success"


def test_automatic_compaction_triggers_when_duplicate_history_is_stale(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(compact_store, "_RUN_INDEX_COMPACT_BYTES", 1)
    monkeypatch.setattr(compact_store, "_RUN_INDEX_COMPACT_STALE_RATIO", 1)
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime)
    run_id = "run_compact_auto"

    _append_update(runtime, audit_id, run_id)
    _append_terminal(runtime, audit_id, run_id)

    lines = _index_lines(tmp_path / ".run-index.ndjson")
    assert len(lines) == 1
    assert lines[0]["run_id"] == run_id
    assert lines[0]["complete"] is True


def test_oversized_auxiliary_index_self_heals_on_next_authoritative_run(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(base_store, "_MAX_RUN_INDEX_BYTES", 1024)
    monkeypatch.setattr(compact_store, "_MAX_RUN_INDEX_BYTES", 1024)
    monkeypatch.setattr(compact_store, "_RUN_INDEX_COMPACT_BYTES", 1)
    monkeypatch.setattr(compact_store, "_RUN_INDEX_COMPACT_STALE_RATIO", 1)

    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime)
    index_path = tmp_path / ".run-index.ndjson"
    index_path.write_text("x" * 1500, encoding="utf-8")

    run_id = "run_compact_oversized"
    _append_terminal(runtime, audit_id, run_id)

    assert index_path.stat().st_size < 1024
    lines = _index_lines(index_path)
    assert len(lines) == 1
    assert lines[0]["run_id"] == run_id

    reloaded = ProductAuditHarness(tmp_path)
    detail = reloaded.run_detail(run_id)
    assert detail is not None
    assert detail["audit_id"] == audit_id


def test_compaction_failure_never_rolls_back_authoritative_event_append(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(compact_store, "_RUN_INDEX_COMPACT_BYTES", 1)
    monkeypatch.setattr(compact_store, "_RUN_INDEX_COMPACT_STALE_RATIO", 1)
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime)
    run_id = "run_compact_failure"
    _append_update(runtime, audit_id, run_id)

    def fail_compaction(*_args, **_kwargs):
        raise OSError("synthetic compaction failure")

    monkeypatch.setattr(runtime.store, "_compact_run_index_locked", fail_compaction)
    _append_terminal(runtime, audit_id, run_id)

    journal = tmp_path / audit_id / "events.ndjson"
    assert run_id in journal.read_text(encoding="utf-8")
    detail = runtime.run_detail(run_id)
    assert detail is not None
    assert detail["status"] == "success"


@pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
def test_run_index_compaction_never_follows_symlink_sidecar(tmp_path) -> None:
    runtime = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(runtime)
    outside = tmp_path / "outside.txt"
    outside.write_text("sentinel", encoding="utf-8")
    index_path = tmp_path / ".run-index.ndjson"
    index_path.symlink_to(outside)

    run_id = "run_compact_symlink"
    _append_terminal(runtime, audit_id, run_id)

    assert outside.read_text(encoding="utf-8") == "sentinel"
    assert index_path.is_symlink()
    detail = runtime.run_detail(run_id)
    assert detail is not None
    assert detail["audit_id"] == audit_id


def test_multi_instance_compaction_preserves_all_server_observed_run_locators(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(compact_store, "_RUN_INDEX_COMPACT_BYTES", 512)
    monkeypatch.setattr(compact_store, "_RUN_INDEX_COMPACT_STALE_RATIO", 1)
    first = ProductAuditHarness(tmp_path)
    audit_id = _seed_audit(first, "Concurrent compaction")
    second = ProductAuditHarness(tmp_path)
    run_ids = [f"run_compact_parallel_{index:03d}" for index in range(80)]

    def append_one(item: tuple[int, str]) -> None:
        index, run_id = item
        runtime = first if index % 2 == 0 else second
        _append_terminal(runtime, audit_id, run_id)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append_one, enumerate(run_ids)))

    assert first.store.compact_run_index() is True
    lines = _index_lines(tmp_path / ".run-index.ndjson")
    assert {str(item["run_id"]) for item in lines} == set(run_ids)
    assert len(lines) == len(run_ids)

    reloaded = ProductAuditHarness(tmp_path)
    for run_id in (run_ids[0], run_ids[17], run_ids[39], run_ids[-1]):
        detail = reloaded.run_detail(run_id)
        assert detail is not None
        assert detail["audit_id"] == audit_id
