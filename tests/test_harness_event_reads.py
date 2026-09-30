from __future__ import annotations

import json

import pytest

from veritas.harness.models import HarnessEvent
from veritas.harness.store import EVENT_JOURNAL_FILENAME, HarnessStore


def _seed_audit(store: HarnessStore) -> str:
    record = store.create_audit(
        title="Bounded event reads",
        filename="paper.pdf",
        pdf_bytes=b"%PDF-1.7\n% bounded event fixture\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 3},
    )
    return str(record["audit_id"])


def test_metadata_only_listing_avoids_hydrating_event_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("veritas.harness.telemetry.export_terminal_run", lambda *_args, **_kwargs: None)
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)
    for index in range(12):
        store.append_event(
            HarnessEvent(
                audit_id=audit_id,
                kind="test",
                title=f"event-{index}",
                payload={"index": index},
            )
        )

    compact = store.list_audits(include_events=False)
    assert len(compact) == 1
    assert compact[0]["audit_id"] == audit_id
    assert compact[0]["events"] == []
    assert compact[0]["event_journal"]["path"] == EVENT_JOURNAL_FILENAME

    hydrated = store.get_audit(audit_id)
    assert [event["payload"]["index"] for event in hydrated["events"]] == list(range(12))


def test_bounded_event_reads_return_exact_tail_in_order(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("veritas.harness.telemetry.export_terminal_run", lambda *_args, **_kwargs: None)
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)
    for index in range(30):
        store.append_event(
            HarnessEvent(
                audit_id=audit_id,
                kind="test",
                title=f"event-{index}",
                payload={"index": index},
            )
        )

    assert [event["payload"]["index"] for event in store.get_events(audit_id, limit=5)] == [
        25,
        26,
        27,
        28,
        29,
    ]
    assert store.get_events(audit_id, limit=0) == []
    assert len(store.get_audit(audit_id, event_limit=7)["events"]) == 7
    assert len(store.list_audits(event_limit=9)[0]["events"]) == 9


def test_bounded_read_validates_earlier_journal_entries_fail_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("veritas.harness.telemetry.export_terminal_run", lambda *_args, **_kwargs: None)
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)
    store.append_event(HarnessEvent(audit_id=audit_id, kind="test", title="first"))
    journal = tmp_path / audit_id / EVENT_JOURNAL_FILENAME
    valid_tail = [
        json.dumps(
            HarnessEvent(audit_id=audit_id, kind="test", title=f"tail-{index}").to_dict(),
            separators=(",", ":"),
        )
        for index in range(8)
    ]
    journal.write_text("{not-json}\n" + "\n".join(valid_tail) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON at line 1"):
        store.get_events(audit_id, limit=3)


def test_large_journal_tail_is_bounded_without_changing_full_read_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("veritas.harness.telemetry.export_terminal_run", lambda *_args, **_kwargs: None)
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)
    store.append_event(HarnessEvent(audit_id=audit_id, kind="test", title="activate"))
    journal = tmp_path / audit_id / EVENT_JOURNAL_FILENAME

    with journal.open("a", encoding="utf-8", newline="\n") as handle:
        for index in range(5_000):
            handle.write(json.dumps({"index": index}, separators=(",", ":")) + "\n")

    tail = store.get_events(audit_id, limit=4)
    assert [event["index"] for event in tail] == [4996, 4997, 4998, 4999]
    assert len(store.get_audit(audit_id)["events"]) == 5_001


def test_legacy_inline_event_limit_works_before_journal_migration(tmp_path) -> None:
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)
    audit_path = tmp_path / audit_id / "audit.json"
    record = json.loads(audit_path.read_text(encoding="utf-8"))
    record["events"] = [{"index": index} for index in range(10)]
    audit_path.write_text(json.dumps(record), encoding="utf-8")

    assert [event["index"] for event in store.get_events(audit_id, limit=3)] == [7, 8, 9]
    assert store.get_events(audit_id, limit=0) == []
    assert [event["index"] for event in store.get_events(audit_id)] == list(range(10))


def test_invalid_event_limits_fail_fast(tmp_path) -> None:
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)

    for invalid in (-1, True, 1.5, "5"):
        with pytest.raises(ValueError, match="non-negative integer"):
            store.get_events(audit_id, limit=invalid)  # type: ignore[arg-type]


def test_append_event_skips_full_rehydration_unless_explicitly_requested(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("veritas.harness.telemetry.export_terminal_run", lambda *_args, **_kwargs: None)
    store = HarnessStore(tmp_path)
    audit_id = _seed_audit(store)

    compact = store.append_event(HarnessEvent(audit_id=audit_id, kind="test", title="compact"))
    assert compact["events"] == []

    hydrated = store.append_event(
        HarnessEvent(audit_id=audit_id, kind="test", title="hydrated"),
        hydrate_result=True,
    )
    assert [event["title"] for event in hydrated["events"]] == ["compact", "hydrated"]
