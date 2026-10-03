from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .benchmark_catalog import benchmark_definition
from .benchmark_results import validate_benchmark_result_payload

_DEFAULT_OUTPUT_DIR = Path("benchmark-result-envelopes")
_ERROR_EXIT_CODE = 127
_MAX_REPORT_BYTES = 1024 * 1024
_REPO_ROOT = Path(__file__).resolve().parents[3]
_AUDITBENCH_OVERALL_METRICS = (
    "cases",
    "papers",
    "alert_precision",
    "alert_recall",
    "clean_papers",
    "false_hard_alert_papers",
    "false_hard_alert_rate_per_clean_paper",
    "grade_violations",
    "grade_violation_rate",
    "status_mismatches",
    "extraction_error_cases",
    "extraction_error_hard_alerts",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _github_context(environ: Mapping[str, str]) -> tuple[str, str | None]:
    commit_sha = environ.get("GITHUB_SHA", "").strip().lower()
    if len(commit_sha) != 40 or any(char not in "0123456789abcdef" for char in commit_sha):
        raise ValueError("GITHUB_SHA must be a full 40-character hexadecimal Git commit")

    repository = environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = environ.get("GITHUB_RUN_ID", "").strip()
    if not repository or not run_id:
        return commit_sha, None

    server_url = environ.get("GITHUB_SERVER_URL", "https://github.com").strip().rstrip("/")
    return commit_sha, f"{server_url}/{repository}/actions/runs/{run_id}"


def _write_envelope(output_dir: Path, benchmark_id: str, payload: dict[str, object]) -> Path:
    validated = validate_benchmark_result_payload(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{benchmark_id}.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(validated, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def _read_json_report(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_REPORT_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"benchmark report unavailable: {path}") from exc
    if len(raw) > _MAX_REPORT_BYTES:
        raise ValueError(f"benchmark report exceeds 1 MiB: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"benchmark report must be UTF-8 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"benchmark report must be a JSON object: {path}")
    return payload


def _auditbench_metrics(
    report_path: Path,
    *,
    expected_benchmark_id: str | None = None,
    expected_pack_id: str | None = None,
) -> dict[str, object]:
    report = _read_json_report(report_path)
    if expected_benchmark_id is not None and report.get("benchmark_id") != expected_benchmark_id:
        raise ValueError("AuditBench CI report benchmark identity does not match catalog")
    if expected_pack_id is not None and report.get("pack_id") != expected_pack_id:
        raise ValueError("AuditBench CI report pack identity does not match catalog")
    if report.get("production_certificate") is not False:
        raise ValueError("AuditBench CI report must explicitly deny production certification")
    if report.get("status") not in {"pass", "fail"}:
        raise ValueError("AuditBench CI report status must be pass or fail")
    overall = report.get("overall")
    if not isinstance(overall, dict):
        raise TypeError("AuditBench CI report overall metrics must be an object")

    metrics: dict[str, object] = {}
    for key in _AUDITBENCH_OVERALL_METRICS:
        if key not in overall:
            raise ValueError(f"AuditBench CI report missing overall metric: {key}")
        value = overall[key]
        if value is not None and not isinstance(value, (bool, int, float, str)):
            raise ValueError(f"AuditBench CI report metric {key} must be a JSON scalar")
        metrics[key] = value

    by_detector = report.get("by_detector")
    if not isinstance(by_detector, dict) or not by_detector:
        raise ValueError("AuditBench CI report must include detector slices")
    metrics["detector_families"] = len(by_detector)
    metrics["production_certificate"] = False
    return metrics


def _adapt_result_metrics(definition: Mapping[str, object]) -> dict[str, object]:
    adapter = definition.get("result_adapter")
    if adapter is None:
        return {}
    if adapter != "auditbench":
        raise ValueError(f"unsupported benchmark result adapter: {adapter}")
    report_path = definition.get("report_path")
    if not isinstance(report_path, str) or not report_path.strip():
        raise ValueError("benchmark result adapter requires report_path")
    report_benchmark_id = definition.get("report_benchmark_id")
    if not isinstance(report_benchmark_id, str) or not report_benchmark_id.strip():
        raise ValueError("AuditBench result adapter requires report_benchmark_id")
    report_pack_id = definition.get("report_pack_id")
    if report_pack_id is not None and not isinstance(report_pack_id, str):
        raise TypeError("AuditBench report_pack_id must be a string when present")
    return _auditbench_metrics(
        _REPO_ROOT / report_path,
        expected_benchmark_id=report_benchmark_id,
        expected_pack_id=report_pack_id,
    )


def run_ci_benchmark(
    benchmark_id: str,
    *,
    output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run one locked catalog command and emit a Benchmark Result Envelope v1.

    The child process inherits stdout/stderr so the workflow log remains the
    benchmark's native output. The returned code mirrors the benchmark command
    when it starts successfully. A successful command whose required report
    cannot be adapted into the product result contract fails closed as exit 127.
    """

    definition = benchmark_definition(benchmark_id)
    command = str(definition["command"])
    title = str(definition["title"])
    commit_sha, run_url = _github_context(os.environ if environ is None else environ)
    started_at = _utc_now_iso()
    return_code = _ERROR_EXIT_CODE
    status = "error"
    summary = f"{title} could not be started."
    metrics: dict[str, object] = {}

    try:
        completed = subprocess.run(shlex.split(command), check=False)
    except OSError as exc:
        summary = f"{title} could not be started ({type(exc).__name__})."
    else:
        return_code = int(completed.returncode)
        status = "passed" if return_code == 0 else "failed"
        summary = f"{title} {status} with exit code {return_code}."
        try:
            metrics = _adapt_result_metrics(definition)
        except (OSError, TypeError, ValueError) as exc:
            if return_code == 0:
                return_code = _ERROR_EXIT_CODE
                status = "error"
                summary = f"{title} passed but its result report could not be adapted ({exc})."
            else:
                summary = f"{summary} Result report could not be adapted ({exc})."

    finished_at = _utc_now_iso()
    payload: dict[str, object] = {
        "schema_version": "1",
        "benchmark_id": benchmark_id,
        "command": command,
        "status": status,
        "source": "ci",
        "started_at": started_at,
        "finished_at": finished_at,
        "commit_sha": commit_sha,
        "run_url": run_url,
        "summary": summary,
        "metrics": metrics,
    }
    _write_envelope(Path(output_dir), benchmark_id, payload)
    return return_code
