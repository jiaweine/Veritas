from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from veritas.harness.benchmark_catalog import benchmark_catalog
from veritas.harness.web import create_app


def test_benchmark_catalog_matches_repository_release_gate_shape() -> None:
    catalog = benchmark_catalog()
    suites = catalog["suites"]

    assert catalog["result_persistence"] is False
    assert catalog["scores_available"] is False
    assert catalog["source_of_truth"] == ".github/workflows/ci.yml"
    assert catalog["gating_count"] == 3
    assert catalog["non_gating_count"] == 4
    assert len(suites) == 7

    by_id = {item["benchmark_id"]: item for item in suites}
    assert by_id["pdf-regression"]["gating"] is True
    assert by_id["pdf-regression"]["command"] == "python scripts/benchmark_pdf_regression.py"
    assert by_id["pdf-geometry-holdout"]["gating"] is True
    assert by_id["extraction-adversarial"]["gating"] is True
    assert by_id["bmc-grouped-headers"]["gating"] is False
    assert by_id["real-pdf-smoke"]["gating"] is False
    assert by_id["real-pdf-fail-closed"]["gating"] is False
    assert by_id["real-pdf-promotion"]["gating"] is False


def test_benchmark_catalog_commands_are_present_in_ci_workflow() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    suites = benchmark_catalog()["suites"]

    for suite in suites:
        assert suite["command"] in workflow
        if suite["gating"]:
            assert "continue-on-error: true\n        run: " + str(suite["command"]) not in workflow


def test_benchmark_catalog_is_exposed_without_synthetic_scores(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/v1/benchmarks")

    assert response.status_code == 200
    catalog = response.json()
    assert catalog["scores_available"] is False
    assert catalog["gating_count"] == 3
    assert all("score" not in suite for suite in catalog["suites"])
