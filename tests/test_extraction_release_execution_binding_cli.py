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
        "scripts/verify_extraction_release_execution_binding.py",
        "--release-bundle",
        str(data["output"]),
        "--release-execution-binding",
        str(data["execution_binding_output"]),
        "--release-artifact-root",
        str(data["release_root"]),
        "--execution-plan",
        str(data["execution_plan_path"]),
        "--development-manifest",
        str(data["development_manifest_path"]),
        "--test-manifest",
        str(data["test_manifest_path"]),
    ]
    for threshold_id, path in sorted(data["development_attestations"].items()):
        args.extend(("--development-attestation", threshold_id, str(path)))
    for threshold_id, path in sorted(data["test_attestations"].items()):
        args.extend(("--test-attestation", threshold_id, str(path)))
    if output is not None:
        args.extend(("--output", str(output)))
    return args


def test_release_execution_binding_verifier_accepts_exact_attestation_chain(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)
    subprocess.run(
        data["args"], cwd=_root(), check=True, capture_output=True, text=True
    )
    output = tmp_path / "verified-release-execution-binding.json"

    result = subprocess.run(
        _verify_args(data, output=output),
        cwd=_root(), check=True, capture_output=True, text=True,
    )

    assert result.stdout == ""
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "release_execution_binding_verified"
    assert payload["production_authorized"] is False
    assert payload["execution_plan_sha256"] == data["execution_plan"].sha256()
    assert payload["development_execution_ids"]
    assert payload["test_execution_ids"]


def test_release_execution_binding_verifier_rejects_attestation_exact_byte_drift(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)
    subprocess.run(
        data["args"], cwd=_root(), check=True, capture_output=True, text=True
    )
    threshold_id = data["fixture"]["test_observations"][0].threshold_id
    path = data["test_attestations"][threshold_id]
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        _verify_args(data), cwd=_root(), check=False, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "release execution binding differs" in result.stderr


def test_release_execution_binding_verifier_rejects_prediction_byte_drift(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)
    subprocess.run(
        data["args"], cwd=_root(), check=True, capture_output=True, text=True
    )
    observation = data["fixture"]["test_observations"][0]
    path = data["release_root"] / f"test/{observation.threshold_id}.json"
    path.write_bytes(path.read_bytes() + b"\n")

    result = subprocess.run(
        _verify_args(data), cwd=_root(), check=False, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "prediction bytes differ from execution attestation" in result.stderr


def test_release_execution_binding_verifier_rejects_execution_plan_exact_byte_drift(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)
    subprocess.run(
        data["args"], cwd=_root(), check=True, capture_output=True, text=True
    )
    payload = json.loads(data["execution_plan_path"].read_text(encoding="utf-8"))
    data["execution_plan_path"].write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        _verify_args(data), cwd=_root(), check=False, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "release execution binding differs" in result.stderr
