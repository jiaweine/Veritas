from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from .benchmark_catalog import benchmark_definition
from .benchmark_results import validate_benchmark_result_payload

_DEFAULT_OUTPUT_DIR = Path(".veritas-benchmark-results")
_ERROR_EXIT_CODE = 127


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


def run_ci_benchmark(
    benchmark_id: str,
    *,
    output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run one locked catalog command and emit a Benchmark Result Envelope v1.

    The child process inherits stdout/stderr so the workflow log remains the
    benchmark's native output. The returned code mirrors the benchmark command
    when it starts successfully; launch errors are represented as exit code 127.
    """

    definition = benchmark_definition(benchmark_id)
    command = str(definition["command"])
    title = str(definition["title"])
    commit_sha, run_url = _github_context(os.environ if environ is None else environ)
    started_at = _utc_now_iso()
    return_code = _ERROR_EXIT_CODE
    status = "error"
    summary = f"{title} could not be started."

    try:
        completed = subprocess.run(shlex.split(command), check=False)  # noqa: S603
    except OSError as exc:
        summary = f"{title} could not be started ({type(exc).__name__})."
    else:
        return_code = int(completed.returncode)
        status = "passed" if return_code == 0 else "failed"
        summary = f"{title} {status} with exit code {return_code}."

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
        "metrics": {},
    }
    _write_envelope(Path(output_dir), benchmark_id, payload)
    return return_code
