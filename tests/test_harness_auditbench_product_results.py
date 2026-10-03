from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from veritas.harness.web import create_app


def _auditbench_payload() -> dict[str, object]:
    return {
        "schema_version": "1",
        "benchmark_id": "auditbench-v1",
        "command": "python scripts/run_auditbench_v1.py",
        "status": "passed",
        "source": "operator",
        "started_at": "2026-10-03T08:00:00Z",
        "finished_at": "2026-10-03T08:00:01Z",
        "commit_sha": None,
        "run_url": None,
        "summary": "Locked AuditBench detector gate passed with exit code 0.",
        "metrics": {
            "cases": 23,
            "papers": 19,
            "alert_precision": 1.0,
            "alert_recall": 1.0,
            "false_hard_alert_rate_per_clean_paper": 0.0,
            "grade_violations": 0,
            "status_mismatches": 0,
            "extraction_error_hard_alerts": 0,
            "detector_families": 7,
            "production_certificate": False,
        },
    }


def test_auditbench_envelope_round_trips_into_benchmark_product_catalog(tmp_path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)

    record = app.state.benchmark_results.ingest(_auditbench_payload())

    catalog_response = client.get("/api/v1/benchmarks")
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    assert catalog["result_count"] == 1
    assert catalog["scores_available"] is False
    latest = catalog["latest_results"]["auditbench-v1"]
    assert latest["result_id"] == record["result_id"]
    assert latest["status"] == "passed"
    assert latest["metrics"]["cases"] == 23
    assert latest["metrics"]["production_certificate"] is False

    listing = client.get("/api/v1/benchmark-results", params={"benchmark_id": "auditbench-v1"})
    assert listing.status_code == 200
    assert listing.json() == [record]


def test_benchmark_ui_prioritizes_synthetic_authority_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "src" / "veritas" / "harness" / "static" / "benchmarks.js").read_text(
        encoding="utf-8"
    )
    styles = (root / "src" / "veritas" / "harness" / "static" / "benchmarks.css").read_text(
        encoding="utf-8"
    )

    assert '"production_certificate"' in script
    assert "Synthetic CI result — not a production certificate." in script
    assert 'data-benchmark-id="${escapeHtml(suite.benchmark_id || "")}"' in script
    assert "No Benchmark Result Envelope v1 has been ingested locally" in script
    assert ".benchmark-authority-note" in styles


def test_benchmark_ui_async_enhancement_is_navigation_safe() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "src" / "veritas" / "harness" / "static" / "benchmarks.js").read_text(
        encoding="utf-8"
    )

    assert "let enhancementGeneration = 0;" in script
    assert 'main.dataset.benchmarksEnhanced = "loading";' in script
    assert "generation !== enhancementGeneration || !benchmarkTitleIsActive()" in script
    assert "enhancementGeneration += 1;" in script
    assert "delete main.dataset.benchmarksEnhanced;" in script
    assert "Loading repository benchmark inventory…" not in script
