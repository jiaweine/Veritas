from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from veritas.harness.models import HarnessEvent
from veritas.harness.store import EVENT_JOURNAL_FILENAME, HarnessStore


def _seed_audit(store: HarnessStore) -> str:
    record = store.create_audit(
        title="Concurrent stress fixture",
        filename="paper.pdf",
        pdf_bytes=b"%PDF-1.7\n% stress fixture\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 3},
    )
    return str(record["audit_id"])


def test_shared_root_stores_preserve_concurrent_event_appends(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("veritas.harness.telemetry.export_terminal_run", lambda *_args, **_kwargs: None)
    stores = [HarnessStore(tmp_path) for _ in range(8)]
    audit_id = _seed_audit(stores[0])
    total = 500

    def append(index: int) -> str:
        event = HarnessEvent(
            audit_id=audit_id,
            kind="stress",
            title=f"event-{index}",
            payload={"index": index},
        )
        stores[index % len(stores)].append_event(event)
        return event.event_id

    with ThreadPoolExecutor(max_workers=24) as pool:
        event_ids = list(pool.map(append, range(total)))

    record = stores[0].get_audit(audit_id)
    persisted = record["events"]
    assert len(persisted) == total
    assert {event["event_id"] for event in persisted} == set(event_ids)
    assert {event["payload"]["index"] for event in persisted} == set(range(total))
    audit_dir = tmp_path / audit_id
    assert list(audit_dir.glob(".audit.json.*.tmp")) == []
    assert list(audit_dir.glob(f".{EVENT_JOURNAL_FILENAME}.*.tmp")) == []


def test_event_journal_keeps_metadata_compact_for_long_traces(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("veritas.harness.telemetry.export_terminal_run", lambda *_args, **_kwargs: None)
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)
    payload = "x" * 4096

    for index in range(300):
        store.append_event(
            HarnessEvent(
                audit_id=audit_id,
                kind="replication",
                title=f"dense-event-{index}",
                detail=payload,
                payload={"index": index, "chunk": payload},
            )
        )

    audit_dir = tmp_path / audit_id
    metadata_path = audit_dir / "audit.json"
    journal_path = audit_dir / EVENT_JOURNAL_FILENAME
    stored_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    journal_lines = journal_path.read_text(encoding="utf-8").splitlines()

    assert stored_metadata["events"] == []
    assert stored_metadata["event_journal"] == {
        "schema_version": "1",
        "path": EVENT_JOURNAL_FILENAME,
    }
    assert metadata_path.stat().st_size < 32 * 1024
    assert len(journal_lines) == 300
    assert journal_path.stat().st_size > metadata_path.stat().st_size * 20
    assert len(store.get_audit(audit_id)["events"]) == 300


def test_legacy_inline_events_migrate_once_without_duplication(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("veritas.harness.telemetry.export_terminal_run", lambda *_args, **_kwargs: None)
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)
    audit_path = tmp_path / audit_id / "audit.json"
    legacy = json.loads(audit_path.read_text(encoding="utf-8"))
    legacy_event = HarnessEvent(
        audit_id=audit_id,
        kind="legacy",
        title="legacy-inline-event",
        payload={"generation": 0},
    ).to_dict()
    legacy["events"] = [legacy_event]
    audit_path.write_text(json.dumps(legacy), encoding="utf-8")

    fresh = HarnessEvent(
        audit_id=audit_id,
        kind="fresh",
        title="fresh-journal-event",
        payload={"generation": 1},
    )
    store.append_event(fresh)

    record = store.get_audit(audit_id)
    assert [event["event_id"] for event in record["events"]] == [
        legacy_event["event_id"],
        fresh.event_id,
    ]
    stored_metadata = json.loads(audit_path.read_text(encoding="utf-8"))
    assert stored_metadata["events"] == []
    journal_lines = (tmp_path / audit_id / EVENT_JOURNAL_FILENAME).read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(journal_lines) == 2


def test_event_journal_corruption_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("veritas.harness.telemetry.export_terminal_run", lambda *_args, **_kwargs: None)
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)
    store.append_event(HarnessEvent(audit_id=audit_id, kind="test", title="valid"))
    journal = tmp_path / audit_id / EVENT_JOURNAL_FILENAME
    with journal.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    with pytest.raises(ValueError, match="invalid JSON"):
        store.get_audit(audit_id)


def test_shared_root_stores_preserve_concurrent_attachment_manifest_updates(tmp_path) -> None:
    stores = [HarnessStore(tmp_path) for _ in range(6)]
    audit_id = _seed_audit(stores[0])
    total = 72

    def attach(index: int) -> str:
        metadata = stores[index % len(stores)].add_attachment(
            audit_id,
            filename=f"artifact-{index}.txt",
            payload=(f"payload-{index}" * 32).encode("utf-8"),
            media_type="text/plain",
        )
        return str(metadata["attachment_id"])

    with ThreadPoolExecutor(max_workers=18) as pool:
        attachment_ids = list(pool.map(attach, range(total)))

    attachments = stores[0].list_attachments(audit_id)
    assert len(attachments) == total
    assert {item["attachment_id"] for item in attachments} == set(attachment_ids)
    for item in attachments:
        path = stores[0].get_attachment_path(audit_id, str(item["attachment_id"]))
        assert path.is_file()
