from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from test_extraction_evidence_workflow import _workflow_fixture

from veritas.benchmark import BenchmarkSplit
from veritas.extraction_calibration_archive import (
    ExtractionDevelopmentCalibrationFreeze,
    ExtractionDevelopmentCalibrationObservationArchive,
    ExtractionTestEvaluationArchive,
    development_calibration_freeze_json_payload,
)
from veritas.extraction_calibration_archive import (
    test_evaluation_archive_json_payload as _test_evaluation_archive_json_payload,
)
from veritas.extraction_evidence_workflow import extraction_evidence_plan_payload
from veritas.extraction_execution_evidence import (
    ExtractionExecutionPlan,
    build_extraction_execution_evidence,
    extraction_prediction_artifact_bytes,
    extraction_prediction_semantics_sha256,
)
from veritas.extraction_execution_evidence_json import (
    extraction_execution_attestation_json_payload,
    extraction_execution_plan_json_payload,
)
from veritas.extraction_input_artifacts import (
    build_extraction_input_artifact_manifest,
    extraction_input_artifact_manifest_payload,
)
from veritas.extraction_release_archive import load_extraction_release_evidence_bundle
from veritas.extraction_release_calibration_binding import (
    load_extraction_release_calibration_binding,
)
from veritas.extraction_release_execution_binding import (
    load_extraction_release_execution_binding,
)
from veritas.extraction_review_record_json import extraction_review_record_json_payload


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pilot_policy_payload(fixture) -> dict[str, object]:
    policy = fixture["policy"]
    return {
        "schema_version": 1,
        "status": "frozen_nonproduction_pilot_threshold_policy",
        "as_of": "2026-09-12",
        "production_authorized": False,
        "bound_evidence_plan_sha256": fixture["plan"].sha256(),
        "benchmark_confidence": fixture["plan"].benchmark_confidence,
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
        "interpretation": "Synthetic non-production release-binding fixture.",
        "production_boundary": "Synthetic fixture only; no production authority.",
    }


def _execution_plan() -> ExtractionExecutionPlan:
    return ExtractionExecutionPlan(
        input_artifact_manifest_sha256="1" * 64,
        source_tree_sha256="2" * 64,
        parser_registry_sha256="3" * 64,
        numerical_runtime_sha256="4" * 64,
        execution_command_sha256="5" * 64,
    )


def _attestation(
    *,
    execution_plan: ExtractionExecutionPlan,
    execution_id: str,
    split: BenchmarkSplit,
    threshold_id: str,
    threshold: float,
    target_manifest_sha256: str,
    prediction_path: Path,
    predictions,
    output: Path,
) -> Path:
    evidence = build_extraction_execution_evidence(
        plan=execution_plan,
        execution_id=execution_id,
        split=split,
        threshold_id=threshold_id,
        threshold=threshold,
        target_manifest_sha256=target_manifest_sha256,
        predictions=predictions,
        prediction_artifact=prediction_path.read_bytes(),
    )
    _write_json(output, extraction_execution_attestation_json_payload(evidence.attestation))
    return output


def _fixture_args(tmp_path: Path):
    fixture = _workflow_fixture()
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    entries = []
    for paper in fixture["frame"].papers:
        relative = f"{paper.paper_id}.pdf"
        (input_root / relative).write_bytes(f"publication:{paper.paper_id}\n".encode())
        entries.append((paper.paper_id, relative))
    manifest = build_extraction_input_artifact_manifest(input_root, tuple(entries))
    manifest_path = tmp_path / "input-manifest.json"
    _write_json(manifest_path, extraction_input_artifact_manifest_payload(manifest))

    review_paths = []
    for record in fixture["review_records"]:
        path = tmp_path / "reviews" / f"{record.target.target_id}.json"
        _write_json(path, extraction_review_record_json_payload(record))
        review_paths.append(path)

    evidence_plan_path = tmp_path / "evidence-plan.json"
    _write_json(
        evidence_plan_path,
        extraction_evidence_plan_payload(fixture["plan"], fixture["grid"]),
    )
    execution_plan = _execution_plan()
    execution_plan_path = tmp_path / "execution-plan.json"
    _write_json(execution_plan_path, extraction_execution_plan_json_payload(execution_plan))
    policy_path = tmp_path / "pilot-policy.json"
    _write_json(policy_path, _pilot_policy_payload(fixture))
    development_manifest_path = tmp_path / "development-target-manifest.json"
    test_manifest_path = tmp_path / "test-target-manifest.json"
    _write_json(development_manifest_path, fixture["development_manifest"].to_payload())
    _write_json(test_manifest_path, fixture["test_manifest"].to_payload())

    release_root = tmp_path / "release-artifacts"
    attestation_root = tmp_path / "attestations"
    development_args = []
    development_attestations: dict[str, Path] = {}
    archived_observations = []
    for observation in fixture["observations"]:
        relative = f"development/{observation.threshold_id}.json"
        path = release_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        predictions = observation.predictions or ()
        path.write_bytes(extraction_prediction_artifact_bytes(predictions))
        attestation_path = _attestation(
            execution_plan=execution_plan,
            execution_id=f"development-{observation.threshold_id}",
            split=BenchmarkSplit.DEVELOPMENT,
            threshold_id=observation.threshold_id,
            threshold=observation.threshold,
            target_manifest_sha256=fixture["development_manifest"].sha256(),
            prediction_path=path,
            predictions=predictions,
            output=attestation_root / "development" / f"{observation.threshold_id}.json",
        )
        development_attestations[observation.threshold_id] = attestation_path
        development_args.append(
            (
                observation.threshold_id,
                relative,
                str(attestation_path),
            )
        )
        archived_observations.append(
            ExtractionDevelopmentCalibrationObservationArchive.from_report(
                threshold_id=observation.threshold_id,
                threshold=observation.threshold,
                prediction_artifact_sha256=_file_sha256(path),
                prediction_semantics_sha256=extraction_prediction_semantics_sha256(predictions),
                report=observation.report,
            )
        )

    freeze = ExtractionDevelopmentCalibrationFreeze(
        evidence_plan_sha256=fixture["plan"].sha256(),
        development_manifest_sha256=fixture["development_manifest"].sha256(),
        benchmark_confidence=fixture["plan"].benchmark_confidence,
        pilot_policy_file_sha256=_file_sha256(policy_path),
        threshold_policy=fixture["policy"],
        observations=tuple(archived_observations),
        selectivity_curve=fixture["development_curve"],
        frozen_threshold=fixture["frozen"],
    )
    freeze_path = tmp_path / "development-calibration-freeze.json"
    _write_json(freeze_path, development_calibration_freeze_json_payload(freeze))

    test_archive = ExtractionTestEvaluationArchive(
        development_calibration_freeze_sha256=freeze.sha256(),
        development_calibration_freeze_file_sha256=_file_sha256(freeze_path),
        frozen_threshold_sha256=freeze.frozen_threshold.sha256(),
        test_manifest_sha256=fixture["test_manifest"].sha256(),
        test_manifest_file_sha256=_file_sha256(test_manifest_path),
        test_evaluation_lock=fixture["test_lock"],
    )
    test_lock_path = tmp_path / "test-evaluation-lock.json"
    _write_json(test_lock_path, _test_evaluation_archive_json_payload(test_archive))

    test_args = []
    test_attestations: dict[str, Path] = {}
    for observation in fixture["test_observations"]:
        relative = f"test/{observation.threshold_id}.json"
        path = release_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        predictions = observation.predictions or ()
        path.write_bytes(extraction_prediction_artifact_bytes(predictions))
        attestation_path = _attestation(
            execution_plan=execution_plan,
            execution_id=f"test-{observation.threshold_id}",
            split=BenchmarkSplit.TEST,
            threshold_id=observation.threshold_id,
            threshold=observation.threshold,
            target_manifest_sha256=fixture["test_manifest"].sha256(),
            prediction_path=path,
            predictions=predictions,
            output=attestation_root / "test" / f"{observation.threshold_id}.json",
        )
        test_attestations[observation.threshold_id] = attestation_path
        test_args.append(
            (
                observation.threshold_id,
                relative,
                str(attestation_path),
            )
        )

    output = tmp_path / "release-bundle.json"
    binding_output = tmp_path / "release-calibration-binding.json"
    execution_binding_output = tmp_path / "release-execution-binding.json"
    args = [
        sys.executable,
        "scripts/build_extraction_release_bundle.py",
        "--release-artifact-root",
        str(release_root),
        "--input-artifact-manifest",
        str(manifest_path),
        "--input-artifact-root",
        str(input_root),
        "--evidence-plan",
        str(evidence_plan_path),
        "--execution-plan",
        str(execution_plan_path),
        "--pilot-threshold-policy",
        str(policy_path),
        "--development-freeze",
        str(freeze_path),
        "--development-manifest",
        str(development_manifest_path),
        "--test-evaluation-lock",
        str(test_lock_path),
        "--test-manifest",
        str(test_manifest_path),
        "--output",
        str(output),
        "--calibration-binding-output",
        str(binding_output),
        "--execution-binding-output",
        str(execution_binding_output),
    ]
    for path in review_paths:
        args.extend(("--review-record", str(path)))
    for run in development_args:
        args.extend(("--development-run", *run))
    for run in test_args:
        args.extend(("--test-run", *run))
    return {
        "fixture": fixture,
        "args": args,
        "output": output,
        "binding_output": binding_output,
        "execution_binding_output": execution_binding_output,
        "input_root": input_root,
        "manifest_path": manifest_path,
        "entries": entries,
        "evidence_plan_path": evidence_plan_path,
        "execution_plan": execution_plan,
        "execution_plan_path": execution_plan_path,
        "policy_path": policy_path,
        "freeze_path": freeze_path,
        "development_manifest_path": development_manifest_path,
        "test_manifest_path": test_manifest_path,
        "test_lock_path": test_lock_path,
        "release_root": release_root,
        "development_attestations": development_attestations,
        "test_attestations": test_attestations,
    }


def test_release_bundle_cli_derives_policy_thresholds_and_execution_ids_from_frozen_chain(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)

    result = subprocess.run(
        data["args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    bundle = load_extraction_release_evidence_bundle(data["output"])
    calibration_binding = load_extraction_release_calibration_binding(data["binding_output"])
    execution_binding = load_extraction_release_execution_binding(data["execution_binding_output"])
    fixture = data["fixture"]
    summary = json.loads(result.stdout)

    assert len(bundle.review_records) == len(fixture["review_records"])
    assert len(bundle.development_runs) == len(fixture["observations"])
    assert len(bundle.test_runs) == len(fixture["test_observations"])
    assert bundle.threshold_policy == fixture["policy"]
    assert tuple(run.threshold for run in bundle.development_runs) == tuple(
        observation.threshold for observation in fixture["observations"]
    )
    assert tuple(run.execution_id for run in bundle.development_runs) == tuple(
        f"development-{observation.threshold_id}" for observation in fixture["observations"]
    )
    assert calibration_binding.release_bundle_sha256 == bundle.sha256()
    assert calibration_binding.frozen_threshold_sha256 == fixture["frozen"].sha256()
    assert execution_binding.release_bundle_sha256 == bundle.sha256()
    assert execution_binding.execution_plan_sha256 == data["execution_plan"].sha256()
    assert summary["release_bundle_sha256"] == bundle.sha256()
    assert summary["release_calibration_binding_sha256"] == calibration_binding.sha256()
    assert summary["release_execution_binding_sha256"] == execution_binding.sha256()
    assert summary["production_authorized"] is False


def test_release_bundle_cli_rejects_review_source_outside_verified_manifest(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)
    incomplete = build_extraction_input_artifact_manifest(
        data["input_root"], tuple(data["entries"][1:])
    )
    _write_json(data["manifest_path"], extraction_input_artifact_manifest_payload(incomplete))

    result = subprocess.run(
        data["args"], cwd=_root(), check=False, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "outside the verified input-artifact manifest" in result.stderr
    assert not data["output"].exists()
    assert not data["execution_binding_output"].exists()


def test_release_bundle_cli_rejects_pilot_policy_exact_byte_drift(tmp_path: Path) -> None:
    data = _fixture_args(tmp_path)
    payload = json.loads(data["policy_path"].read_text(encoding="utf-8"))
    data["policy_path"].write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        data["args"], cwd=_root(), check=False, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "different pilot-policy bytes" in result.stderr
    assert not data["execution_binding_output"].exists()


def test_release_bundle_cli_rejects_test_manifest_exact_byte_drift(tmp_path: Path) -> None:
    data = _fixture_args(tmp_path)
    payload = json.loads(data["test_manifest_path"].read_text(encoding="utf-8"))
    data["test_manifest_path"].write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        data["args"], cwd=_root(), check=False, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "different TEST manifest bytes" in result.stderr
    assert not data["execution_binding_output"].exists()


def test_release_bundle_cli_rejects_test_attestation_prediction_hash_drift(tmp_path: Path) -> None:
    data = _fixture_args(tmp_path)
    threshold_id = data["fixture"]["test_observations"][0].threshold_id
    path = data["test_attestations"][threshold_id]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["prediction_artifact_sha256"] = "f" * 64
    _write_json(path, payload)

    result = subprocess.run(
        data["args"], cwd=_root(), check=False, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "prediction bytes differ from execution attestation" in result.stderr
    assert not data["execution_binding_output"].exists()


def test_release_bundle_cli_has_no_manual_policy_threshold_or_execution_id_surface(
    tmp_path: Path,
) -> None:
    data = _fixture_args(tmp_path)
    args = list(data["args"])
    args.extend(("--min-selective-coverage", "0.123"))

    result = subprocess.run(
        args, cwd=_root(), check=False, capture_output=True, text=True
    )
    help_text = subprocess.run(
        [sys.executable, "scripts/build_extraction_release_bundle.py", "--help"],
        cwd=_root(), check=True, capture_output=True, text=True,
    ).stdout

    assert result.returncode != 0
    assert "unrecognized arguments: --min-selective-coverage" in result.stderr
    assert "THRESHOLD_ID PREDICTION_ARTIFACT_PATH EXECUTION_ATTESTATION" in help_text
    assert "THRESHOLD_ID EXECUTION_ID" not in help_text
