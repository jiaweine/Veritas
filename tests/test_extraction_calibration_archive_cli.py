from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_extraction_split_manifest_cli import _fixture as _split_fixture

from veritas.extraction import ExtractionDecision, ExtractionResolution
from veritas.extraction_benchmark import ExtractionPrediction
from veritas.extraction_calibration import ExtractionThresholdPolicy
from veritas.extraction_calibration_archive import (
    load_development_calibration_freeze,
    load_pretest_pilot_threshold_policy,
    load_test_evaluation_archive,
)
from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_execution_evidence import extraction_prediction_artifact_bytes


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _arg_path(args: list[str], flag: str) -> Path:
    return Path(args[args.index(flag) + 1])


def _pilot_policy_payload(plan_sha256: str, policy: ExtractionThresholdPolicy) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "frozen_nonproduction_pilot_threshold_policy",
        "as_of": "2026-09-11",
        "production_authorized": False,
        "bound_evidence_plan_sha256": plan_sha256,
        "benchmark_confidence": 0.95,
        "threshold_policy": {
            "schema_version": policy.schema_version,
            "min_selective_coverage": policy.min_selective_coverage,
            "min_accepted_full_accuracy": policy.min_accepted_full_accuracy,
            "max_critical_family_wrong_accept_upper_bound": (
                policy.max_critical_family_wrong_accept_upper_bound
            ),
        },
        "threshold_policy_sha256": policy.sha256(),
        "current_design_power": {},
        "interpretation": "Synthetic non-production calibration policy fixture.",
        "production_boundary": "Synthetic fixture only; no production authority.",
    }


def _calibration_fixture(tmp_path: Path):
    split_args, split_output, _, record_paths = _split_fixture(tmp_path)
    subprocess.run(
        split_args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    development_manifest_path = split_output / "development-target-manifest.json"
    test_manifest_path = split_output / "test-target-manifest.json"
    development_manifest = load_extraction_split_target_manifest(development_manifest_path)

    evidence_plan_path = _arg_path(split_args, "--evidence-plan")
    plan, _ = load_extraction_evidence_plan(evidence_plan_path)
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.0,
        min_accepted_full_accuracy=0.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    policy_path = tmp_path / "pilot-policy.json"
    _write_json(policy_path, _pilot_policy_payload(plan.sha256(), policy))

    prediction_path = tmp_path / "development-nc-010.json"
    predictions = tuple(
        ExtractionPrediction(
            target_id=target_id,
            resolution=ExtractionResolution(
                decision=ExtractionDecision.ABSTAIN,
                normalized_value=None,
                accepted_candidates=(),
                calibration_threshold=0.01,
                reason="synthetic DEVELOPMENT calibration fixture",
            ),
        )
        for target_id in development_manifest.target_ids
    )
    prediction_path.write_bytes(extraction_prediction_artifact_bytes(predictions))

    freeze_path = tmp_path / "development-calibration-freeze.json"
    freeze_args = [
        sys.executable,
        "scripts/freeze_extraction_development_threshold.py",
        "--sampling-frame",
        str(_arg_path(split_args, "--sampling-frame")),
        "--seed-manifest",
        str(_arg_path(split_args, "--seed-manifest")),
        "--evidence-plan",
        str(evidence_plan_path),
        "--pilot-threshold-policy",
        str(policy_path),
        "--development-manifest",
        str(development_manifest_path),
        "--development-prediction",
        "nc-010",
        str(prediction_path),
        "--output",
        str(freeze_path),
    ]
    for path in record_paths:
        freeze_args.extend(("--review-record", str(path)))

    return {
        "split_args": split_args,
        "split_output": split_output,
        "development_manifest_path": development_manifest_path,
        "test_manifest_path": test_manifest_path,
        "policy_path": policy_path,
        "prediction_path": prediction_path,
        "freeze_path": freeze_path,
        "freeze_args": freeze_args,
        "plan": plan,
        "policy": policy,
        "predictions": predictions,
    }


def test_development_freeze_and_test_lock_are_separate_pretest_steps(tmp_path: Path) -> None:
    fixture = _calibration_fixture(tmp_path)

    freeze_result = subprocess.run(
        fixture["freeze_args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    freeze_summary = json.loads(freeze_result.stdout)
    freeze = load_development_calibration_freeze(fixture["freeze_path"])

    assert freeze.frozen_threshold.threshold_id == "nc-010"
    assert freeze.frozen_threshold.threshold == 0.01
    assert freeze.threshold_policy == fixture["policy"]
    assert freeze.evidence_plan_sha256 == fixture["plan"].sha256()
    assert freeze.pilot_policy_file_sha256 == hashlib.sha256(
        fixture["policy_path"].read_bytes()
    ).hexdigest()
    assert freeze.observations[0].prediction_artifact_sha256 == hashlib.sha256(
        fixture["prediction_path"].read_bytes()
    ).hexdigest()
    assert freeze_summary["development_calibration_freeze_sha256"] == freeze.sha256()
    assert freeze_summary["production_authorized"] is False

    lock_path = tmp_path / "test-evaluation-lock.json"
    lock_result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_test_evaluation_lock.py",
            "--development-freeze",
            str(fixture["freeze_path"]),
            "--development-manifest",
            str(fixture["development_manifest_path"]),
            "--test-manifest",
            str(fixture["test_manifest_path"]),
            "--output",
            str(lock_path),
        ],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    lock_summary = json.loads(lock_result.stdout)
    archive = load_test_evaluation_archive(lock_path)
    test_manifest = load_extraction_split_target_manifest(fixture["test_manifest_path"])

    assert archive.development_calibration_freeze_sha256 == freeze.sha256()
    assert archive.development_calibration_freeze_file_sha256 == hashlib.sha256(
        fixture["freeze_path"].read_bytes()
    ).hexdigest()
    assert archive.frozen_threshold_sha256 == freeze.frozen_threshold.sha256()
    assert archive.test_manifest_sha256 == test_manifest.sha256()
    assert archive.test_evaluation_lock.frozen_threshold_sha256 == (
        freeze.frozen_threshold.sha256()
    )
    assert lock_summary["test_evaluation_archive_sha256"] == archive.sha256()
    assert lock_summary["production_authorized"] is False


def test_development_freeze_rejects_policy_bound_to_other_plan(tmp_path: Path) -> None:
    fixture = _calibration_fixture(tmp_path)
    payload = json.loads(fixture["policy_path"].read_text(encoding="utf-8"))
    payload["bound_evidence_plan_sha256"] = "f" * 64
    _write_json(fixture["policy_path"], payload)

    result = subprocess.run(
        fixture["freeze_args"],
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "pilot threshold policy is bound to a different evidence plan" in result.stderr
    assert not fixture["freeze_path"].exists()


def test_development_freeze_rejects_prediction_threshold_drift(tmp_path: Path) -> None:
    fixture = _calibration_fixture(tmp_path)
    drifted = tuple(
        ExtractionPrediction(
            target_id=prediction.target_id,
            resolution=ExtractionResolution(
                decision=prediction.resolution.decision,
                normalized_value=prediction.resolution.normalized_value,
                accepted_candidates=prediction.resolution.accepted_candidates,
                calibration_threshold=0.02,
                reason=prediction.resolution.reason,
            ),
        )
        for prediction in fixture["predictions"]
    )
    fixture["prediction_path"].write_bytes(extraction_prediction_artifact_bytes(drifted))

    result = subprocess.run(
        fixture["freeze_args"],
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "prediction calibration threshold differs from precommitted grid" in result.stderr
    assert not fixture["freeze_path"].exists()


def test_development_freeze_rejects_test_manifest_as_calibration_input(tmp_path: Path) -> None:
    fixture = _calibration_fixture(tmp_path)
    args = list(fixture["freeze_args"])
    args[args.index("--development-manifest") + 1] = str(fixture["test_manifest_path"])

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "supplied DEVELOPMENT manifest differs" in result.stderr
    assert not fixture["freeze_path"].exists()


def test_test_lock_rejects_split_lock_drift(tmp_path: Path) -> None:
    fixture = _calibration_fixture(tmp_path)
    subprocess.run(
        fixture["freeze_args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    test_manifest_payload = json.loads(
        fixture["test_manifest_path"].read_text(encoding="utf-8")
    )
    test_manifest_payload["split_lock_sha256"] = "e" * 64
    drifted_test_manifest = tmp_path / "drifted-test-manifest.json"
    _write_json(drifted_test_manifest, test_manifest_payload)
    lock_path = tmp_path / "test-evaluation-lock.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_test_evaluation_lock.py",
            "--development-freeze",
            str(fixture["freeze_path"]),
            "--development-manifest",
            str(fixture["development_manifest_path"]),
            "--test-manifest",
            str(drifted_test_manifest),
            "--output",
            str(lock_path),
        ],
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "use different article-family split locks" in result.stderr
    assert not lock_path.exists()


def test_calibration_archive_strict_loaders_reject_tampered_hashes_and_boolean_schema(
    tmp_path: Path,
) -> None:
    fixture = _calibration_fixture(tmp_path)
    subprocess.run(
        fixture["freeze_args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    freeze_payload = json.loads(fixture["freeze_path"].read_text(encoding="utf-8"))

    bad_threshold_hash = tmp_path / "bad-threshold-hash.json"
    _write_json(
        bad_threshold_hash,
        {**freeze_payload, "frozen_threshold_sha256": "0" * 64},
    )
    with pytest.raises(ValueError, match="frozen-threshold SHA-256 differs"):
        load_development_calibration_freeze(bad_threshold_hash)

    bad_schema = tmp_path / "bad-schema.json"
    _write_json(bad_schema, {**freeze_payload, "schema_version": True})
    with pytest.raises(TypeError, match="schema_version must be integer 1"):
        load_development_calibration_freeze(bad_schema)

    policy = load_pretest_pilot_threshold_policy(fixture["policy_path"])
    assert policy.bound_evidence_plan_sha256 == fixture["plan"].sha256()
    assert policy.threshold_policy == fixture["policy"]
