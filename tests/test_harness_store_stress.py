from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from veritas.harness.models import HarnessEvent
from veritas.harness.store import HarnessStore


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
    assert list((tmp_path / audit_id).glob(".audit.json.*.tmp")) == []


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
