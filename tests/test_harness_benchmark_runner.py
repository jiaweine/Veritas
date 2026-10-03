from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

import pytest

from veritas.harness import benchmark_runner
from veritas.harness.benchmark_catalog import benchmark_catalog
from veritas.harness.benchmark_results import validate_benchmark_result_payload


def _github_env() -> dict[str, str]:
    return {
        "GITHUB_SHA": "b" * 40,
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "jiaweine/Veritas",
        "GITHUB_RUN_ID": "123456",
    }


def _auditbench_report(**overrides: object) -> dict[str, object]:
    overall: dict[str, object] = {
        "cases": 23,
        "papers": 19,
        "expected_alerts": 8,
        "observed_alerts": 8,
        "true_alerts": 8,
        "false_alerts": 0,
        "missed_alerts": 0,
        "status_mismatches": 0,
        "alert_precision": 1.0,
        "alert_recall": 1.0,
        "clean_papers": 19,
        "false_hard_alert_papers": 0,
        "false_hard_alert_rate_per_clean_paper": 0.0,
        "grade_violations": 0,
        "grade_violation_rate": 0.0,
        "extraction_error_cases": 5,
        "extraction_error_hard_alerts": 0,
    }
    payload: dict[str, object] = {
        "schema_version": 1,
        "benchmark_id": "auditbench-synthetic-v1",
        "status": "pass",
        "production_certificate": False,
        "overall": overall,
        "by_detector": {"regression_consistency": overall},
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "suite",
    benchmark_catalog()["suites"],
    ids=lambda suite: str(suite["benchmark_id"]),
)
def test_ci_runner_executes_exact_catalog_command_and_emits_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suite: dict[str, object],
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert check is False
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(benchmark_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(benchmark_runner, "_adapt_result_metrics", lambda _definition: {})
    benchmark_id = str(suite["benchmark_id"])

    return_code = benchmark_runner.run_ci_benchmark(
        benchmark_id,
        output_dir=tmp_path,
        environ=_github_env(),
    )

    assert return_code == 0
    assert calls == [shlex.split(str(suite["command"]))]
    payload = json.loads((tmp_path / f"{benchmark_id}.json").read_text(encoding="utf-8"))
    assert payload == validate_benchmark_result_payload(payload)
    assert payload["benchmark_id"] == benchmark_id
    assert payload["command"] == suite["command"]
    assert payload["status"] == "passed"
    assert payload["source"] == "ci"
    assert payload["commit_sha"] == "b" * 40
    assert payload["run_url"] == "https://github.com/jiaweine/Veritas/actions/runs/123456"
    assert payload["metrics"] == {}


def test_auditbench_adapter_projects_only_safe_scalar_metrics(tmp_path: Path) -> None:
    report = tmp_path / "auditbench.json"
    report.write_text(json.dumps(_auditbench_report()), encoding="utf-8")

    metrics = benchmark_runner._auditbench_metrics(report)

    assert metrics["cases"] == 23
    assert metrics["papers"] == 19
    assert metrics["alert_precision"] == 1.0
    assert metrics["alert_recall"] == 1.0
    assert metrics["false_hard_alert_rate_per_clean_paper"] == 0.0
    assert metrics["grade_violations"] == 0
    assert metrics["status_mismatches"] == 0
    assert metrics["extraction_error_hard_alerts"] == 0
    assert metrics["detector_families"] == 1
    assert metrics["production_certificate"] is False
    assert "by_detector" not in metrics
    assert "observations" not in metrics


def test_auditbench_adapter_rejects_production_certificate_claim(tmp_path: Path) -> None:
    report = tmp_path / "auditbench.json"
    report.write_text(
        json.dumps(_auditbench_report(production_certificate=True)),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="deny production certification"):
        benchmark_runner._auditbench_metrics(report)


def test_successful_benchmark_fails_closed_when_required_report_cannot_be_adapted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert command == ["python", "scripts/run_auditbench_v1.py"]
        assert check is False
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(benchmark_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        benchmark_runner,
        "_adapt_result_metrics",
        lambda _definition: (_ for _ in ()).throw(ValueError("missing raw report")),
    )

    return_code = benchmark_runner.run_ci_benchmark(
        "auditbench-v1",
        output_dir=tmp_path,
        environ=_github_env(),
    )

    payload = json.loads((tmp_path / "auditbench-v1.json").read_text(encoding="utf-8"))
    assert return_code == 127
    assert payload["status"] == "error"
    assert "passed but its result report could not be adapted" in payload["summary"]
    assert payload["metrics"] == {}


def test_ci_runner_preserves_nonzero_exit_code_and_emits_failed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert check is False
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(benchmark_runner.subprocess, "run", fake_run)

    return_code = benchmark_runner.run_ci_benchmark(
        "pdf-regression",
        output_dir=tmp_path,
        environ=_github_env(),
    )

    payload = json.loads((tmp_path / "pdf-regression.json").read_text(encoding="utf-8"))
    assert return_code == 7
    assert payload["status"] == "failed"
    assert "exit code 7" in payload["summary"]


def test_ci_runner_emits_error_when_command_cannot_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        del command, check
        raise FileNotFoundError("python executable unavailable")

    monkeypatch.setattr(benchmark_runner.subprocess, "run", fake_run)

    return_code = benchmark_runner.run_ci_benchmark(
        "pdf-regression",
        output_dir=tmp_path,
        environ=_github_env(),
    )

    payload = json.loads((tmp_path / "pdf-regression.json").read_text(encoding="utf-8"))
    assert return_code == 127
    assert payload["status"] == "error"
    assert "FileNotFoundError" in payload["summary"]


def test_ci_runner_rejects_missing_commit_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("benchmark command must not start without a valid GITHUB_SHA")

    monkeypatch.setattr(benchmark_runner.subprocess, "run", fail_if_called)

    with pytest.raises(ValueError, match="GITHUB_SHA"):
        benchmark_runner.run_ci_benchmark(
            "pdf-regression",
            output_dir=tmp_path,
            environ={},
        )

    assert list(tmp_path.iterdir()) == []
