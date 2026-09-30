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
