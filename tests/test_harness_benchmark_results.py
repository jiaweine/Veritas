from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from veritas.harness.benchmark_results import BenchmarkResultStore
from veritas.harness.web import create_app


def test_benchmark_result_store_is_append_only_and_sorted(tmp_path) -> None:
    store = BenchmarkResultStore(tmp_path / "benchmark-results")
    first = store.record(
        benchmark_id="pdf-regression",
        exit_code=0,
        commit_sha="abcdef1",
        duration_ms=1200,
        recorded_at="2026-09-16T10:00:00+00:00",
    )
    second = store.record(
        benchmark_id="pdf-regression",
        exit_code=1,
        commit_sha="abcdef2",
        duration_ms=1400,
        recorded_at="2026-09-16T11:00:00+00:00",
    )

    results = store.list_results()
    assert [item["result_id"] for item in results] == [second["result_id"], first["result_id"]]
    assert results[0]["status"] == "failed"
    assert results[0]["exit_code"] == 1
    assert results[1]["status"] == "passed"
    assert results[1]["payload_sha256"]


def test_benchmark_result_store_rejects_unknown_suite_and_invalid_provenance(tmp_path) -> None:
    store = BenchmarkResultStore(tmp_path / "benchmark-results")

    with pytest.raises(ValueError, match="unknown benchmark id"):
        store.record(benchmark_id="invented-score", exit_code=0)
    with pytest.raises(ValueError, match="commit_sha"):
        store.record(benchmark_id="pdf-regression", exit_code=0, commit_sha="not-a-commit")
    with pytest.raises(ValueError, match="duration_ms"):
        store.record(benchmark_id="pdf-regression", exit_code=0, duration_ms=-1)


def test_benchmark_result_hash_tamper_fails_closed(tmp_path) -> None:
    store = BenchmarkResultStore(tmp_path / "benchmark-results")
    result = store.record(benchmark_id="pdf-regression", exit_code=0, commit_sha="abcdef1")
    path = store.root / "pdf-regression" / f"{result['result_id']}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["exit_code"] = 9
    path.chmod(0o644)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        store.list_results()


def test_benchmark_api_exposes_empty_persistence_without_scores(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    catalog_response = client.get("/api/v1/benchmarks")
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    assert catalog["result_persistence"] is True
    assert catalog["results_available"] is False
    assert catalog["result_count"] == 0
    assert catalog["scores_available"] is False
    assert all(item["latest_result"] is None for item in catalog["suites"])

    results_response = client.get("/api/v1/benchmarks/results")
    assert results_response.status_code == 200
    assert results_response.json() == {
        "schema_version": "1",
        "scores_available": False,
        "results": [],
    }


def test_benchmark_api_projects_real_persisted_execution(tmp_path) -> None:
    app = create_app(tmp_path)
    stored = app.state.benchmark_results.record(
        benchmark_id="pdf-regression",
        exit_code=0,
        commit_sha="abcdef1",
        duration_ms=321,
        recorded_at="2026-09-16T12:00:00+00:00",
    )
    client = TestClient(app)

    catalog = client.get("/api/v1/benchmarks").json()
    assert catalog["results_available"] is True
    assert catalog["result_count"] == 1
    pdf_regression = next(
        item for item in catalog["suites"] if item["benchmark_id"] == "pdf-regression"
    )
    assert pdf_regression["latest_result"]["result_id"] == stored["result_id"]
    assert pdf_regression["latest_result"]["status"] == "passed"
    assert "score" not in pdf_regression["latest_result"]

    response = client.get("/api/v1/benchmarks/results?benchmark_id=pdf-regression&limit=1")
    assert response.status_code == 200
    assert response.json()["results"][0]["result_id"] == stored["result_id"]


def test_benchmark_api_surfaces_integrity_failure(tmp_path) -> None:
    app = create_app(tmp_path)
    stored = app.state.benchmark_results.record(benchmark_id="pdf-regression", exit_code=0)
    path = (
        app.state.benchmark_results.root
        / "pdf-regression"
        / f"{stored['result_id']}.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "failed"
    path.chmod(0o644)
    path.write_text(json.dumps(payload), encoding="utf-8")
    client = TestClient(app)

    response = client.get("/api/v1/benchmarks")
    assert response.status_code == 409
    assert "hash mismatch" in response.json()["detail"]
