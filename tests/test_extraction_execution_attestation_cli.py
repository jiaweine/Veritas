from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from test_extraction_evidence_workflow import _workflow_fixture
from test_extraction_execution_evidence import _execution_plan

from veritas.extraction_evidence_plan_json import extraction_evidence_plan_json_payload
from veritas.extraction_execution_evidence import extraction_prediction_artifact_bytes
from veritas.extraction_execution_evidence_json import (
    extraction_execution_plan_json_payload,
    load_extraction_execution_attestation,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fixture(tmp_path: Path):
    fixture = _workflow_fixture()
    execution_plan = _execution_plan()
    observation = fixture["observations"][0]

    execution_plan_path = tmp_path / "execution-plan.json"
    _write_json(execution_plan_path, extraction_execution_plan_json_payload(execution_plan))

    evidence_plan_path = tmp_path / "evidence-plan.json"
    _write_json(
        evidence_plan_path,
        extraction_evidence_plan_json_payload(fixture["plan"], fixture["grid"]),
    )

    target_manifest_path = tmp_path / "development-target-manifest.json"
    _write_json(target_manifest_path, fixture["development_manifest"].to_payload())

    prediction_path = tmp_path / "predictions.json"
    prediction_path.write_bytes(extraction_prediction_artifact_bytes(observation.predictions or ()))

    output_path = tmp_path / "attestation.json"
    args = [
        sys.executable,
        "scripts/build_extraction_execution_attestation.py",
        "--execution-plan",
        str(execution_plan_path),
        "--evidence-plan",
        str(evidence_plan_path),
        "--target-manifest",
        str(target_manifest_path),
        "--prediction-artifact",
        str(prediction_path),
        "--execution-id",
        "development-run-001",
        "--threshold-id",
        observation.threshold_id,
        "--output",
        str(output_path),
    ]
    return fixture, observation, prediction_path, output_path, args


def test_execution_attestation_cli_builds_strict_archive(tmp_path: Path) -> None:
    fixture, observation, prediction_path, output_path, args = _fixture(tmp_path)

    result = subprocess.run(
        args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    attestation = load_extraction_execution_attestation(output_path)

    assert attestation.execution_id == "development-run-001"
    assert attestation.split.value == "DEVELOPMENT"
    assert attestation.threshold_id == observation.threshold_id
    assert attestation.threshold == observation.threshold
    assert attestation.target_manifest_sha256 == fixture["development_manifest"].sha256()
    assert attestation.prediction_artifact_sha256 == hashlib.sha256(
        prediction_path.read_bytes()
    ).hexdigest()
    assert summary["attestation_sha256"] == attestation.sha256()
    assert summary["attestation_file_sha256"] == hashlib.sha256(
        output_path.read_bytes()
    ).hexdigest()
    assert summary["prediction_semantics_sha256"] == attestation.prediction_semantics_sha256
    assert summary["production_authorized"] is False


def test_execution_attestation_cli_rejects_unknown_threshold(tmp_path: Path) -> None:
    _, _, _, output_path, args = _fixture(tmp_path)
    args[args.index("--threshold-id") + 1] = "not-precommitted"

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "threshold_id is not present in the precommitted grid" in result.stderr
    assert not output_path.exists()


def test_execution_attestation_cli_rejects_prediction_membership_drift(tmp_path: Path) -> None:
    _, observation, prediction_path, output_path, args = _fixture(tmp_path)
    predictions = tuple(observation.predictions or ())
    assert predictions
    prediction_path.write_bytes(extraction_prediction_artifact_bytes(predictions[:-1]))

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "prediction artifact target membership differs from target manifest" in result.stderr
    assert not output_path.exists()


def test_execution_attestation_cli_rejects_noncanonical_prediction_bytes(tmp_path: Path) -> None:
    _, _, prediction_path, output_path, args = _fixture(tmp_path)
    prediction_path.write_bytes(prediction_path.read_bytes() + b"\n")

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "prediction artifact bytes do not use the canonical JSON contract" in result.stderr
    assert not output_path.exists()
