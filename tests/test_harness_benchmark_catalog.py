from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from veritas.harness.benchmark_catalog import benchmark_catalog
from veritas.harness.web import create_app


def test_benchmark_catalog_matches_repository_release_gate_shape() -> None:
    catalog = benchmark_catalog()
    suites = catalog["suites"]

    assert catalog["result_persistence"] is True
    assert catalog["results_available"] is False
    assert catalog["result_count"] == 0
    assert catalog["scores_available"] is False
    assert catalog["result_schema_version"] == "1"
    assert catalog["source_of_truth"] == ".github/workflows/ci.yml"
    assert catalog["gating_count"] == 5
    assert catalog["non_gating_count"] == 4
    assert len(suites) == 9

    by_id = {item["benchmark_id"]: item for item in suites}
    assert by_id["auditbench-v1"]["gating"] is True
    assert by_id["auditbench-v1"]["command"] == "python scripts/run_auditbench_v1.py"
    assert by_id["auditbench-v1"]["report_path"] == "auditbench-raw-reports/auditbench-v1.json"
    assert by_id["auditbench-v1"]["result_adapter"] == "auditbench"
    assert by_id["auditbench-v02-pack"]["gating"] is True
    assert by_id["auditbench-v02-pack"]["command"] == "python scripts/run_auditbench_v02_pack.py"
    assert by_id["auditbench-v02-pack"]["report_path"] == (
        "auditbench-raw-reports/auditbench-v02-pack.json"
    )
    assert by_id["auditbench-v02-pack"]["result_adapter"] == "auditbench"
    assert by_id["pdf-regression"]["gating"] is True
    assert by_id["pdf-regression"]["command"] == "python scripts/benchmark_pdf_regression.py"
    assert by_id["pdf-geometry-holdout"]["gating"] is True
    assert by_id["extraction-adversarial"]["gating"] is True
    assert by_id["bmc-grouped-headers"]["gating"] is False
    assert by_id["real-pdf-smoke"]["gating"] is False
    assert by_id["real-pdf-fail-closed"]["gating"] is False
    assert by_id["real-pdf-promotion"]["gating"] is False


def test_benchmark_catalog_suites_are_enveloped_in_ci_without_changing_gate_semantics() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    suites = benchmark_catalog()["suites"]

    for suite in suites:
        wrapper = f"python scripts/run_benchmark_enveloped.py {suite['benchmark_id']}"
        assert wrapper in workflow
        non_gating_block = "continue-on-error: true\n        run: " + wrapper
        if suite["gating"]:
            assert non_gating_block not in workflow
        else:
            assert non_gating_block in workflow

    assert "if: always()\n        uses: actions/upload-artifact@" in workflow
    assert "path: benchmark-result-envelopes/*.json" in workflow
    assert "path: auditbench-raw-reports/*.json" in workflow
    assert "veritas-auditbench-reports-${{ github.run_id }}-${{ github.run_attempt }}" in workflow


def test_auditbench_raw_reports_are_not_written_into_standard_envelope_directory() -> None:
    root = Path(__file__).resolve().parents[1]
    v1 = (root / "scripts" / "run_auditbench_v1.py").read_text(encoding="utf-8")
    v02 = (root / "scripts" / "run_auditbench_v02_pack.py").read_text(encoding="utf-8")

    assert 'DEFAULT_OUTPUT = ROOT / "auditbench-raw-reports/auditbench-v1.json"' in v1
    assert 'DEFAULT_OUTPUT = ROOT / "auditbench-raw-reports/auditbench-v02-pack.json"' in v02
    assert "benchmark-result-envelopes/auditbench" not in v1
    assert "benchmark-result-envelopes/auditbench" not in v02


def test_benchmark_catalog_is_exposed_without_synthetic_scores(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/v1/benchmarks")

    assert response.status_code == 200
    catalog = response.json()
    assert catalog["result_persistence"] is True
    assert catalog["results_available"] is False
    assert catalog["result_count"] == 0
    assert catalog["scores_available"] is False
    assert catalog["gating_count"] == 5
    assert len(catalog["suites"]) == 9
    assert all("score" not in suite for suite in catalog["suites"])
