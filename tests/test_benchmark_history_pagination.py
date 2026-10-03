from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veritas.harness.benchmark_pagination import BenchmarkHistoryIndex
from veritas.harness.benchmark_results import BenchmarkResultStore
from veritas.harness.web import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "veritas" / "harness" / "static"


def _payload(index: int) -> dict[str, object]:
    finished = datetime(2026, 10, 3, 16, 0, tzinfo=UTC) - timedelta(minutes=index)
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
        "summary": f"Benchmark history fixture {index + 1}.",
        "metrics": {"cases": 48, "verification_rate": 1.0},
    }


def _seed(store: BenchmarkResultStore, count: int = 60) -> list[dict[str, object]]:
    return [store.ingest(_payload(index)) for index in range(count)]


def test_history_index_bounds_steady_state_envelope_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = BenchmarkResultStore(tmp_path)
    records = _seed(store)
    history = BenchmarkHistoryIndex(store)

    first = history.page(limit=50)
    assert len(first["items"]) == 50
    assert first["has_more"] is True
    assert first["total"] == 60
    assert first["next_cursor"]

    original = store._read_result
    reads: list[str] = []

    def counted(result_id: str) -> dict[str, object]:
        reads.append(result_id)
        return original(result_id)

    monkeypatch.setattr(store, "_read_result", counted)

    second = history.page(limit=50, cursor=str(first["next_cursor"]))
    assert len(second["items"]) == 10
    assert second["has_more"] is False
    assert second["total"] == 60
    assert len(reads) == 10

    reads.clear()
    total, latest = history.catalog_snapshot()
    assert total == 60
    assert [item["result_id"] for item in latest] == [records[0]["result_id"]]
    assert len(reads) == 1

    reads.clear()
    legacy = history.list_results(limit=7)
    assert len(legacy) == 7
    assert len(reads) == 7


def test_history_index_detects_sidecar_tampering(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)
    _seed(store, 3)
    history = BenchmarkHistoryIndex(store)
    history.page(limit=1)

    history.index_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="index changed outside the store|index hash mismatch"):
        history.page(limit=1)


def test_benchmark_page_api_is_keyset_bounded_and_catalog_keeps_total(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    records = _seed(app.state.benchmark_results)
    client = TestClient(app)

    first = client.get("/api/v1/benchmark-result-pages", params={"limit": 50})
    assert first.status_code == 200
    payload = first.json()
    assert len(payload["items"]) == 50
    assert payload["items"][0]["result_id"] == records[0]["result_id"]
    assert payload["total"] == 60
    assert payload["has_more"] is True
    assert payload["next_cursor"]

    second = client.get(
        "/api/v1/benchmark-result-pages",
        params={"limit": 50, "cursor": payload["next_cursor"]},
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 10
    assert second.json()["has_more"] is False
    assert len(
        {
            item["result_id"]
            for item in payload["items"] + second.json()["items"]
        }
    ) == 60

    catalog = client.get("/api/v1/benchmarks")
    assert catalog.status_code == 200
    assert catalog.json()["result_count"] == 60
    latest = catalog.json()["latest_results"]["pdf-regression"]
    assert latest["result_id"] == records[0]["result_id"]

    legacy = client.get("/api/v1/benchmark-results", params={"limit": 5})
    assert legacy.status_code == 200
    assert len(legacy.json()) == 5

    invalid_cursor = client.get(
        "/api/v1/benchmark-result-pages", params={"cursor": "not-a-cursor"}
    )
    assert invalid_cursor.status_code == 422
    assert (
        client.get(
            "/api/v1/benchmark-result-pages",
            params={"benchmark_id": "not-a-benchmark"},
        ).status_code
        == 422
    )


def test_benchmark_catalog_still_fails_closed_on_latest_envelope_tamper(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    records = _seed(app.state.benchmark_results, 3)
    client = TestClient(app)
    assert client.get("/api/v1/benchmarks").status_code == 200

    latest = records[0]
    path = app.state.benchmark_results.root / f"{latest['result_id']}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["duration_ms"] = 1
    path.chmod(0o644)
    path.write_text(json.dumps(value), encoding="utf-8")

    response = client.get("/api/v1/benchmarks")
    assert response.status_code == 500
    assert "integrity error" in response.json()["detail"]


def test_benchmarks_product_uses_cursor_history_without_legacy_materialization() -> None:
    script = (STATIC / "benchmarks.js").read_text(encoding="utf-8")
    styles = (STATIC / "benchmarks.css").read_text(encoding="utf-8")
    service_worker = (STATIC / "sw.js").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts" / "smoke_benchmarks_browser.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ui-visual-smoke.yml").read_text(encoding="utf-8")

    assert "const BENCHMARK_PAGE_LIMIT = 50" in script
    assert "/api/v1/benchmark-result-pages" in script
    assert "/api/v1/benchmark-results?" not in script
    assert "seen.has(item.result_id)" in script
    assert "data-benchmark-load-more" in script
    assert "Unable to load the next benchmark result page" in script
    assert "Loaded all" in script
    assert "previousScrollY" in script
    assert "Persisted result history" in script
    assert ".benchmark-history-footer" in styles
    assert ".benchmark-history-error" in styles

    # Preserve prior cache-key contracts while changing sw.js so the browser
    # installs a fresh worker and re-adds the shell assets into the same cache.
    assert 'const CACHE = "veritas-shell-v29";' in service_worker
    assert 'const CACHE_REVISION = "audit-pagination-1";' in service_worker
    assert 'const ACTIVE_CACHE = `${CACHE}-${CACHE_REVISION}`;' in service_worker
    assert 'const FINDING_CACHE_REVISION = "finding-pagination-1";' in service_worker
    assert 'const SHELL_CACHE = `${ACTIVE_CACHE}-${FINDING_CACHE_REVISION}`;' in service_worker
    assert 'const BENCHMARK_CACHE_REVISION = "benchmark-history-1";' in service_worker
    assert "caches.open(SHELL_CACHE)" in service_worker

    assert '"first_page_rows": 50' in smoke
    assert '"total_rows": 60' in smoke
    assert '"legacy_list_requests": len(legacy_list_requests)' in smoke
    assert "Benchmarks pagination introduced duplicate result rows" in smoke
    assert "benchmarks-history-60.png" in smoke
    assert "python scripts/smoke_benchmarks_browser.py" in workflow
