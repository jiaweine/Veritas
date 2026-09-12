from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_extraction_release_bundle_cli import _fixture_args


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _verify_args(data, *, output: Path | None = None) -> list[str]:
    args = [
        sys.executable,
        "scripts/verify_extraction_release_calibration_binding.py",
        "--release-bundle",
        str(data["output"]),
        "--release-calibration-binding",
        str(data["binding_output"]),
        "--release-artifact-root",
        str(data["release_root"]),
        "--evidence-plan",
        str(Path(data["args"][data["args"].index("--evidence-plan") + 1])),
        "--pilot-threshold-policy",
        str(data["policy_path"]),
        "--development-freeze",
        str(data["freeze_path"]),
        "--development-manifest",
        str(Path(data["args"][data["args"].index("--development-manifest") + 1])),
        "--test-evaluation-lock",
        str(data["test_lock_path"]),
        "--test-manifest",
        str(data["test_manifest_path"]),
    ]
    if output is not None:
        args.extend(("--output", str(output)))
    return args


def test_release_calibration_binding_verifier_accepts_exact_frozen_chain(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)
    subprocess.run(
        data["args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    output = tmp_path / "verified-release-calibration-binding.json"

    result = subprocess.run(
        _verify_args(data, output=output),
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == ""
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "release_calibration_binding_verified"
    assert payload["production_authorized"] is False
    assert payload["selected_threshold_id"] == data["fixture"]["frozen"].threshold_id


def test_release_calibration_binding_verifier_rejects_release_bundle_byte_drift(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)
    subprocess.run(
        data["args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(data["output"].read_text(encoding="utf-8"))
    data["output"].write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        _verify_args(data),
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "release calibration binding differs" in result.stderr


def test_release_calibration_binding_verifier_rejects_frozen_development_prediction_drift(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)
    subprocess.run(
        data["args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    development_run = data["fixture"]["observations"][0]
    path = data["release_root"] / f"development/{development_run.threshold_id}.json"
    path.write_bytes(path.read_bytes() + b"\n")

    result = subprocess.run(
        _verify_args(data),
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "release DEVELOPMENT prediction bytes differ" in result.stderr
