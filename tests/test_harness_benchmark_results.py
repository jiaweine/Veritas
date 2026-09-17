from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veritas.harness import benchmark_cli, benchmark_results
from veritas.harness.benchmark_results import BenchmarkResultStore
from veritas.harness.web import create_app


def _payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1",
        "benchmark_id": "pdf-regression",
        "command": "python scripts/benchmark_pdf_regression.py",
        "status": "passed",
        "source": "ci",
        "started_at": "2026-09-16T15:00:00Z",
        "finished_at": "2026-09-16T15:00:02.500Z",
        "commit_sha": "a" * 40,
        "run_url": "https://github.com/jiaweine/Veritas/actions/runs/123",
        "summary": "Locked PDF regression benchmark passed.",
        "metrics": {"cases": 4, "verification_rate": 1.0, "fail_closed": True},
    }
    value.update(overrides)
    return value


def test_store_ingest_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)
    source = json.dumps(_payload(), indent=2).encode()
    compact_source = json.dumps(_payload(), separators=(",", ":")).encode()

    first = store.ingest(_payload(), source_bytes=source)
    second = store.ingest(_payload(), source_bytes=compact_source)

    assert first["result_id"].startswith("bmr_")
    assert second == first
    assert first["duration_ms"] == 2500
    assert first["source_sha256"]
    assert first["payload_sha256"]
    assert first["record_sha256"]
    assert store.get_result(str(first["result_id"])) == first
    assert store.list_results() == [first]


def test_store_fails_closed_on_result_id_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = BenchmarkResultStore(tmp_path)
    first = store.ingest(_payload())
    different_payload = _payload(summary="Semantically different result sharing a forced short id.")
    monkeypatch.setattr(
        benchmark_results,
        "_result_id_from_payload_sha256",
        lambda _payload_sha256: str(first["result_id"]),
    )

    with pytest.raises(ValueError, match="benchmark result id collision"):
        store.ingest(different_payload)


def test_store_rejects_unknown_or_mismatched_benchmark_contract(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)

    with pytest.raises(ValueError, match="unknown benchmark id"):
        store.ingest(_payload(benchmark_id="made-up"))
    with pytest.raises(ValueError, match="command does not match catalog"):
        store.ingest(_payload(command="python anything.py"))
    with pytest.raises(ValueError, match="commit_sha is required"):
        store.ingest(_payload(commit_sha=None))
    with pytest.raises(ValueError, match="JSON scalar"):
        store.ingest(_payload(metrics={"nested": {"not": "allowed"}}))
    with pytest.raises(ValueError, match="duplicate metric key"):
        store.ingest(_payload(metrics={"cases": 4, " cases ": 5}))
    with pytest.raises(ValueError, match="timezone offset"):
        store.ingest(_payload(started_at="2026-09-16T15:00:00"))
    with pytest.raises(ValueError, match="unknown benchmark result fields"):
        store.ingest(_payload(extra_provenance="silently dropping this would be unsafe"))
    mismatched_source = json.dumps(_payload(status="failed")).encode()
    with pytest.raises(ValueError, match="does not match payload"):
        store.ingest(_payload(), source_bytes=mismatched_source)


def test_store_detects_local_result_tampering(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)
    record = store.ingest(_payload())
    path = store.root / f"{record['result_id']}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["status"] = "failed"
    path.chmod(0o644)
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="record hash mismatch"):
        store.get_result(str(record["result_id"]))


def test_store_record_hash_covers_outer_provenance(tmp_path: Path) -> None:
    store = BenchmarkResultStore(tmp_path)
    record = store.ingest(_payload())
    path = store.root / f"{record['result_id']}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["source_sha256"] = "0" * 64
    path.chmod(0o644)
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="record hash mismatch"):
        store.get_result(str(record["result_id"]))


def test_benchmark_result_api_reports_empty_and_persisted_states(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)

    empty = client.get("/api/v1/benchmarks")
    assert empty.status_code == 200
    assert empty.json()["results_available"] is False
    assert empty.json()["result_count"] == 0
    assert client.get("/api/v1/benchmark-results").json() == []

    record = app.state.benchmark_results.ingest(_payload())

    catalog = client.get("/api/v1/benchmarks")
    assert catalog.status_code == 200
    payload = catalog.json()
    assert payload["results_available"] is True
    assert payload["result_count"] == 1
    assert payload["scores_available"] is False
    assert payload["latest_results"]["pdf-regression"]["result_id"] == record["result_id"]

    listing = client.get("/api/v1/benchmark-results", params={"benchmark_id": "pdf-regression"})
    assert listing.status_code == 200
    assert listing.json() == [record]

    detail = client.get(f"/api/v1/benchmark-results/{record['result_id']}")
    assert detail.status_code == 200
    assert detail.json() == record
    assert client.get("/api/v1/benchmark-results", params={"benchmark_id": "unknown"}).status_code == 422
    assert client.get("/api/v1/benchmark-results/bmr_0000000000000000").status_code == 404


def test_benchmark_result_api_fails_closed_on_store_tamper(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    record = app.state.benchmark_results.ingest(_payload())
    path = app.state.benchmark_results.root / f"{record['result_id']}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["duration_ms"] = 1
    path.chmod(0o644)
    path.write_text(json.dumps(value), encoding="utf-8")

    response = client.get("/api/v1/benchmarks")
    assert response.status_code == 500
    assert "integrity error" in response.json()["detail"]


def test_operator_cli_ingests_validated_envelope(tmp_path: Path) -> None:
    source = tmp_path / "result.json"
    source.write_text(json.dumps(_payload(source="operator", commit_sha=None)), encoding="utf-8")
    data_dir = tmp_path / "harness"
    args = argparse.Namespace(result_file=source, data_dir=str(data_dir))

    record = benchmark_cli.run(args)

    assert record["source"] == "operator"
    assert record["commit_sha"] is None
    assert BenchmarkResultStore(data_dir).get_result(str(record["result_id"])) == record


def test_operator_cli_rejects_oversized_source_without_unbounded_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "oversized.json"
    source.write_bytes(b" " * (benchmark_cli._MAX_RESULT_FILE_BYTES + 1))
    data_dir = tmp_path / "harness"
    args = argparse.Namespace(result_file=source, data_dir=str(data_dir))

    def fail_read_bytes(_path: Path) -> bytes:
        raise AssertionError("benchmark CLI must not read an unbounded source with Path.read_bytes()")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    with pytest.raises(ValueError, match="benchmark result source exceeds 1 MiB"):
        benchmark_cli.run(args)
