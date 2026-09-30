from __future__ import annotations

import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from veritas.harness.models import HarnessEvent
from veritas.harness.store import HarnessStore
from veritas.replication.acp import _InteractiveControlPlane, _jsonable

_EVENT_WRITES = 800
_ATTACHMENT_WRITES = 128
_CONTROL_CYCLES = 20_000
_PAYLOAD_ROUNDS = 500


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def _stress_store(root: Path) -> dict[str, object]:
    stores = [HarnessStore(root) for _ in range(12)]
    record = stores[0].create_audit(
        title="Harness stress fixture",
        filename="paper.pdf",
        pdf_bytes=b"%PDF-1.7\n% stress fixture\n%%EOF\n",
        paper_summary={"pages": 1, "tables_detected": 0, "words": 3},
    )
    audit_id = str(record["audit_id"])

    started = time.perf_counter()

    def append_event(index: int) -> str:
        event = HarnessEvent(
            audit_id=audit_id,
            kind="stress",
            title=f"event-{index}",
            detail="concurrent append",
            payload={"index": index},
        )
        stores[index % len(stores)].append_event(event)
        return event.event_id

    with ThreadPoolExecutor(max_workers=32) as pool:
        event_ids = list(pool.map(append_event, range(_EVENT_WRITES)))
    event_seconds = _elapsed(started)

    started = time.perf_counter()

    def add_attachment(index: int) -> str:
        metadata = stores[index % len(stores)].add_attachment(
            audit_id,
            filename=f"artifact-{index}.txt",
            payload=(f"payload-{index}-" * 64).encode("utf-8"),
            media_type="text/plain",
        )
        return str(metadata["attachment_id"])

    with ThreadPoolExecutor(max_workers=24) as pool:
        attachment_ids = list(pool.map(add_attachment, range(_ATTACHMENT_WRITES)))
    attachment_seconds = _elapsed(started)

    final_record = stores[0].get_audit(audit_id)
    events = final_record["events"]
    attachments = final_record["attachments"]
    assert len(events) == _EVENT_WRITES
    assert {item["event_id"] for item in events} == set(event_ids)
    assert {int(item["payload"]["index"]) for item in events} == set(range(_EVENT_WRITES))
    assert len(attachments) == _ATTACHMENT_WRITES
    assert {item["attachment_id"] for item in attachments} == set(attachment_ids)
    assert list((root / audit_id).glob(".audit.json.*.tmp")) == []

    for metadata in attachments:
        stores[0].get_attachment_path(audit_id, str(metadata["attachment_id"]))

    return {
        "audit_id": audit_id,
        "event_writes": _EVENT_WRITES,
        "event_seconds": event_seconds,
        "attachment_writes": _ATTACHMENT_WRITES,
        "attachment_seconds": attachment_seconds,
    }


def _stress_control_plane() -> dict[str, object]:
    control = _InteractiveControlPlane()
    started = time.perf_counter()
    for index in range(_CONTROL_CYCLES):
        run_id = f"run_{index:012x}"
        control.activate(run_id, interactive_permissions=index % 2 == 0)
        state = control.state(run_id)
        assert state["active"] is True
        if index % 3 == 0:
            assert control.cancel(run_id) is True
            assert control.state(run_id)["cancel_requested"] is True
        control.deactivate(run_id)
        assert control.state(run_id)["active"] is False
    return {
        "control_cycles": _CONTROL_CYCLES,
        "control_seconds": _elapsed(started),
    }


def _stress_agent_payload_bounding() -> dict[str, object]:
    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(16):
        child: dict[str, object] = {}
        cursor["child"] = child
        cursor = child
    payload = {
        "content": {"text": "x" * 100_000},
        "items": list(range(1_000)),
        "mapping": {f"key-{index}": "y" * 1_000 for index in range(1_000)},
        "nested": nested,
    }

    started = time.perf_counter()
    last: dict[str, object] | None = None
    for _ in range(_PAYLOAD_ROUNDS):
        last = _jsonable(payload)
    assert last is not None
    rendered = json.dumps(last, ensure_ascii=False, sort_keys=True)
    assert len(rendered) < 500_000
    assert "truncated" in rendered
    assert "maximum JSON depth" in rendered
    return {
        "payload_rounds": _PAYLOAD_ROUNDS,
        "payload_seconds": _elapsed(started),
        "bounded_payload_bytes": len(rendered.encode("utf-8")),
    }


def main() -> int:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="veritas-harness-stress-") as raw:
        store_metrics = _stress_store(Path(raw))
    control_metrics = _stress_control_plane()
    payload_metrics = _stress_agent_payload_bounding()
    report = {
        "status": "passed",
        "total_seconds": _elapsed(started),
        **store_metrics,
        **control_metrics,
        **payload_metrics,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
