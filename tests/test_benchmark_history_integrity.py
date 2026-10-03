from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from veritas.harness.benchmark_pagination import BenchmarkHistoryIndex, _index_sha256
from veritas.harness.benchmark_results import BenchmarkResultStore


def _payload_at(finished: datetime, index: int) -> dict[str, object]:
    started = finished - timedelta(seconds=2)
    return {
        "schema_version": "1",
        "benchmark_id": "pdf-regression",
        "command": "python scripts/benchmark_pdf_regression.py",
        "status": "passed",
        "source": "ci",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "commit_sha": f"{index + 1:040x}",
        "run_url": f"https://github.com/jiaweine/Veritas/actions/runs/{index + 1}",
        "summary": f"Benchmark ordering fixture {index + 1}.",
        "metrics": {"cases": 48, "verification_rate": 1.0},
    }


def test_keyset_orders_fractional_timestamps_chronologically(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)
    whole_second = datetime(2026, 10, 3, 16, 0, 0, tzinfo=UTC)
    half_second_later = whole_second + timedelta(microseconds=500_000)
    older = store.ingest(_payload_at(whole_second, 0))
    newer = store.ingest(_payload_at(half_second_later, 1))
    history = BenchmarkHistoryIndex(store)

    first = history.page(limit=1)
    assert [item["result_id"] for item in first["items"]] == [newer["result_id"]]
    assert first["has_more"] is True

    second = history.page(limit=1, cursor=str(first["next_cursor"]))
    assert [item["result_id"] for item in second["items"]] == [older["result_id"]]
    assert second["has_more"] is False


def test_index_metadata_is_cross_checked_against_verified_envelope(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)
    store.ingest(_payload_at(datetime(2026, 10, 3, 16, 0, tzinfo=UTC), 0))
    history = BenchmarkHistoryIndex(store)
    history.page(limit=1)

    payload = json.loads(history.index_path.read_text(encoding="utf-8"))
    payload["entries"][0]["benchmark_id"] = "real-pdf-smoke"
    payload["index_sha256"] = _index_sha256(payload)
    history.index_path.write_text(json.dumps(payload), encoding="utf-8")

    # Simulate a syntactically self-consistent sidecar. The result envelope is
    # still authoritative, so metadata disagreement must fail closed even when
    # the attacker/recovery process also refreshed the sidecar marker.
    fresh = max(
        history.index_path.stat().st_mtime_ns,
        history.root.stat().st_mtime_ns,
    ) + 1_000_000
    os.utime(history.marker_path, ns=(fresh, fresh))

    with pytest.raises(ValueError, match="benchmark_id mismatch"):
        history.catalog_snapshot()
