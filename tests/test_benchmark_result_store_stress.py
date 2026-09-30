from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from veritas.harness.benchmark_results import BenchmarkResultStore


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1",
        "benchmark_id": "pdf-regression",
        "command": "python scripts/benchmark_pdf_regression.py",
        "status": "passed",
        "source": "ci",
        "started_at": "2026-09-16T15:00:00Z",
        "finished_at": "2026-09-16T15:00:02.500Z",
        "commit_sha": "a" * 40,
        "run_url": "https://github.com/jiaweine/Veritas/actions/runs/123",
        "summary": "Concurrent idempotent benchmark ingest.",
        "metrics": {"cases": 4, "verification_rate": 1.0},
    }


def test_many_store_instances_idempotently_ingest_same_result(tmp_path) -> None:
    stores = [BenchmarkResultStore(tmp_path) for _ in range(12)]
    total = 160

    def ingest(index: int) -> dict[str, object]:
        return stores[index % len(stores)].ingest(_payload())

    with ThreadPoolExecutor(max_workers=32) as pool:
        records = list(pool.map(ingest, range(total)))

    result_ids = {str(record["result_id"]) for record in records}
    assert len(result_ids) == 1
    result_id = result_ids.pop()
    assert all(record == records[0] for record in records)
    assert stores[0].get_result(result_id) == records[0]
    assert stores[0].list_results(limit=None) == [records[0]]
    assert list(stores[0].root.glob(".*.tmp")) == []
