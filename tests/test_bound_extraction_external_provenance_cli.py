from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from test_extraction_external_provenance_cli import _archived_fixture, _root, _write_json

from veritas.benchmark import BenchmarkSplit
from veritas.extraction_benchmark import (
    build_extraction_selectivity_curve,
    evaluate_extraction_benchmark,
)
from veritas.extraction_calibration import (
    ExtractionThresholdObservation,
    lock_test_evaluation,
    select_development_threshold,
)
from veritas.extraction_calibration_archive import (
    ExtractionDevelopmentCalibrationFreeze,
    ExtractionDevelopmentCalibrationObservationArchive,
    ExtractionTestEvaluationArchive,
    development_calibration_freeze_json_payload,
    load_pretest_pilot_threshold_policy,
)
from veritas.extraction_calibration_archive import (
    test_evaluation_archive_json_payload as _test_evaluation_archive_json_payload,
)
from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_evidence_workflow import (
    build_extraction_split_target_manifest,
    load_extraction_seed_manifest,
)
from veritas.extraction_execution_evidence import (
    build_extraction_execution_evidence,
    extraction_prediction_semantics_sha256,
)
from veritas.extraction_execution_evidence_json import (
    extraction_execution_attestation_json_payload,
    load_extraction_execution_plan,
)
from veritas.extraction_release_archive import (
    load_extraction_prediction_artifact,
    load_extraction_release_evidence_bundle,
)
from veritas.extraction_release_calibration_binding import (
    build_extraction_release_calibration_binding,
    extraction_release_calibration_binding_json_payload,
)
from veritas.extraction_release_execution_binding import (
    build_extraction_release_execution_binding,
    extraction_release_execution_binding_json_payload,
)
from veritas.extraction_review import build_extraction_gold_manifest


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _arg(args: list[str], name: str) -> str:
    return args[args.index(name) + 1]


def _gold_subset(gold, target_ids):
    selected = set(target_ids)
    return tuple(target for target in gold.targets if target.target_id in selected)


def _pilot_policy_payload(plan, policy) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "frozen_nonproduction_pilot_threshold_policy",
        "as_of": "2026-09-12",
        "production_authorized": False,
        "bound_evidence_plan_sha256": plan.sha256(),
        "benchmark_confidence": plan.benchmark_confidence,
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
        "interpretation": "Synthetic bound cold-verification fixture.",
        "production_boundary": "Synthetic fixture only; no production authority.",
    }


def _observations(bundle_runs, gold, *, split: BenchmarkSplit, artifact_root: Path, confidence: float):
    result = []
    for run in bundle_runs:
        prediction_path = artifact_root / run.prediction_artifact_path
        predictions = load_extraction_prediction_artifact(prediction_path)
        result.append(
            ExtractionThresholdObservation(
                threshold_id=run.threshold_id,
                threshold=run.threshold,
                split=split,
                report=evaluate_extraction_benchmark(
                    gold,
                    predictions,
                    confidence=confidence,
                ),
                predictions=predictions,
            )
        )
    return tuple(result)


def _write_attestations(
    *,
    runs,
    split: BenchmarkSplit,
    target_manifest,
    execution_plan,
    artifact_root: Path,
    output_root: Path,
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for run in runs:
        prediction_path = artifact_root / run.prediction_artifact_path
        predictions = load_extraction_prediction_artifact(prediction_path)
        evidence = build_extraction_execution_evidence(
            plan=execution_plan,
            execution_id=run.execution_id,
            split=split,
            threshold_id=run.threshold_id,
            threshold=run.threshold,
            target_manifest_sha256=target_manifest.sha256(),
            predictions=predictions,
            prediction_artifact=prediction_path.read_bytes(),
        )
        path = output_root / split.value / f"{run.threshold_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(
            path,
            extraction_execution_attestation_json_payload(evidence.attestation),
        )
        result[run.threshold_id] = path
    return result


def _bound_fixture(tmp_path: Path):
    fixture = _archived_fixture(tmp_path)
    base_args = fixture["args"]
    seed_path = Path(_arg(base_args, "--seed-manifest"))
    evidence_plan_path = Path(_arg(base_args, "--evidence-plan"))
    execution_plan_path = Path(_arg(base_args, "--execution-plan"))

    seed_manifest = load_extraction_seed_manifest(seed_path)
    plan, grid = load_extraction_evidence_plan(evidence_plan_path)
    bundle = load_extraction_release_evidence_bundle(fixture["bundle_path"])
    execution_plan = load_extraction_execution_plan(execution_plan_path)

    gold = build_extraction_gold_manifest(
        bundle.review_records,
        split_salt=plan.split_salt,
        source_seed_manifest_sha256=seed_manifest.source_manifest_sha256,
        review_protocol_version=plan.review_protocol_version,
    )
    split_lock = gold.build_split_lock(
        train_fraction=plan.train_fraction,
        development_fraction=plan.development_fraction,
    )
    development_manifest = build_extraction_split_target_manifest(
        gold,
        split_lock,
        split=BenchmarkSplit.DEVELOPMENT,
    )
    test_manifest = build_extraction_split_target_manifest(
        gold,
        split_lock,
        split=BenchmarkSplit.TEST,
    )
    development_manifest_path = tmp_path / "development-target-manifest.json"
    test_manifest_path = tmp_path / "test-target-manifest.json"
    _write_json(development_manifest_path, development_manifest.to_payload())
    _write_json(test_manifest_path, test_manifest.to_payload())

    pilot_policy_path = tmp_path / "pilot-policy.json"
    _write_json(pilot_policy_path, _pilot_policy_payload(plan, bundle.threshold_policy))
    pilot_policy = load_pretest_pilot_threshold_policy(pilot_policy_path)

    development_gold = _gold_subset(gold, development_manifest.target_ids)
    test_gold = _gold_subset(gold, test_manifest.target_ids)
    development_observations = _observations(
        bundle.development_runs,
        development_gold,
        split=BenchmarkSplit.DEVELOPMENT,
        artifact_root=fixture["release_artifact_root"],
        confidence=plan.benchmark_confidence,
    )
    test_observations = _observations(
        bundle.test_runs,
        test_gold,
        split=BenchmarkSplit.TEST,
        artifact_root=fixture["release_artifact_root"],
        confidence=plan.benchmark_confidence,
    )
    frozen = select_development_threshold(
        development_observations,
        policy=bundle.threshold_policy,
        development_manifest_sha256=development_manifest.sha256(),
    )
    development_curve = build_extraction_selectivity_curve(
        tuple(
            (observation.threshold, observation.report)
            for observation in development_observations
        )
    )
    archived_observations = tuple(
        ExtractionDevelopmentCalibrationObservationArchive.from_report(
            threshold_id=observation.threshold_id,
            threshold=observation.threshold,
            prediction_artifact_sha256=_file_sha256(
                fixture["release_artifact_root"]
                / next(
                    run.prediction_artifact_path
                    for run in bundle.development_runs
                    if run.threshold_id == observation.threshold_id
                )
            ),
            prediction_semantics_sha256=extraction_prediction_semantics_sha256(
                observation.predictions or ()
            ),
            report=observation.report,
        )
        for observation in development_observations
    )
    development_freeze = ExtractionDevelopmentCalibrationFreeze(
        evidence_plan_sha256=plan.sha256(),
        development_manifest_sha256=development_manifest.sha256(),
        benchmark_confidence=plan.benchmark_confidence,
        pilot_policy_file_sha256=_file_sha256(pilot_policy_path),
        threshold_policy=bundle.threshold_policy,
        observations=archived_observations,
        selectivity_curve=development_curve,
        frozen_threshold=frozen,
    )
    development_freeze_path = tmp_path / "development-calibration-freeze.json"
    _write_json(
        development_freeze_path,
        development_calibration_freeze_json_payload(development_freeze),
    )

    test_evaluation_lock = lock_test_evaluation(
        frozen,
        test_manifest_sha256=test_manifest.sha256(),
    )
    test_evaluation_archive = ExtractionTestEvaluationArchive(
        development_calibration_freeze_sha256=development_freeze.sha256(),
        development_calibration_freeze_file_sha256=_file_sha256(development_freeze_path),
        frozen_threshold_sha256=frozen.sha256(),
        test_manifest_sha256=test_manifest.sha256(),
        test_manifest_file_sha256=_file_sha256(test_manifest_path),
        test_evaluation_lock=test_evaluation_lock,
    )
    test_evaluation_lock_path = tmp_path / "test-evaluation-lock.json"
    _write_json(
        test_evaluation_lock_path,
        _test_evaluation_archive_json_payload(test_evaluation_archive),
    )

    calibration_binding = build_extraction_release_calibration_binding(
        bundle=bundle,
        bundle_path=fixture["bundle_path"],
        plan=plan,
        threshold_grid_sha256=grid.sha256(),
        pilot_policy=pilot_policy,
        pilot_policy_path=pilot_policy_path,
        development_freeze=development_freeze,
        development_freeze_path=development_freeze_path,
        development_manifest=development_manifest,
        development_manifest_path=development_manifest_path,
        test_evaluation_archive=test_evaluation_archive,
        test_evaluation_archive_path=test_evaluation_lock_path,
        test_manifest=test_manifest,
        test_manifest_path=test_manifest_path,
        release_artifact_root=fixture["release_artifact_root"],
    )
    calibration_binding_path = tmp_path / "release-calibration-binding.json"
    _write_json(
        calibration_binding_path,
        extraction_release_calibration_binding_json_payload(calibration_binding),
    )

    attestation_root = tmp_path / "attestations"
    development_attestations = _write_attestations(
        runs=bundle.development_runs,
        split=BenchmarkSplit.DEVELOPMENT,
        target_manifest=development_manifest,
        execution_plan=execution_plan,
        artifact_root=fixture["release_artifact_root"],
        output_root=attestation_root,
    )
    test_attestations = _write_attestations(
        runs=bundle.test_runs,
        split=BenchmarkSplit.TEST,
        target_manifest=test_manifest,
        execution_plan=execution_plan,
        artifact_root=fixture["release_artifact_root"],
        output_root=attestation_root,
    )
    execution_binding = build_extraction_release_execution_binding(
        bundle=bundle,
        bundle_path=fixture["bundle_path"],
        execution_plan=execution_plan,
        execution_plan_path=execution_plan_path,
        development_manifest=development_manifest,
        test_manifest=test_manifest,
        release_artifact_root=fixture["release_artifact_root"],
        development_attestation_paths=development_attestations,
        test_attestation_paths=test_attestations,
    )
    execution_binding_path = tmp_path / "release-execution-binding.json"
    _write_json(
        execution_binding_path,
        extraction_release_execution_binding_json_payload(execution_binding),
    )

    output_path = tmp_path / "bound-cold-verification.json"
    args = list(base_args)
    args[1] = "scripts/verify_bound_extraction_external_provenance.py"
    args[args.index("--output") + 1] = str(output_path)
    args.extend(
        (
            "--release-calibration-binding",
            str(calibration_binding_path),
            "--pilot-threshold-policy",
            str(pilot_policy_path),
            "--development-freeze",
            str(development_freeze_path),
            "--development-manifest",
            str(development_manifest_path),
            "--test-evaluation-lock",
            str(test_evaluation_lock_path),
            "--test-manifest",
            str(test_manifest_path),
            "--release-execution-binding",
            str(execution_binding_path),
        )
    )
    for threshold_id, path in development_attestations.items():
        args.extend(("--development-attestation", threshold_id, str(path)))
    for threshold_id, path in test_attestations.items():
        args.extend(("--test-attestation", threshold_id, str(path)))

    return {
        **fixture,
        "args": args,
        "output_path": output_path,
        "calibration_binding": calibration_binding,
        "calibration_binding_path": calibration_binding_path,
        "execution_binding": execution_binding,
        "execution_binding_path": execution_binding_path,
        "pilot_policy_path": pilot_policy_path,
        "development_attestations": development_attestations,
        "test_attestations": test_attestations,
        "test_observations": test_observations,
    }


def test_bound_external_provenance_cli_verifies_bindings_and_cold_rebuild_together(
    tmp_path: Path,
) -> None:
    fixture = _bound_fixture(tmp_path)
    result = subprocess.run(
        fixture["args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(fixture["output_path"].read_text(encoding="utf-8"))
    assert payload["status"] == "bound_external_provenance_verified"
    assert payload["production_authorized"] is False
    assert payload["release_calibration_binding_sha256"] == fixture[
        "calibration_binding"
    ].sha256()
    assert payload["release_execution_binding_sha256"] == fixture[
        "execution_binding"
    ].sha256()
    assert payload["release_calibration_binding_file_sha256"] == _file_sha256(
        fixture["calibration_binding_path"]
    )
    assert payload["release_execution_binding_file_sha256"] == _file_sha256(
        fixture["execution_binding_path"]
    )
    assert payload["receipt"]["production_authorized"] is False
    assert result.stdout.strip() == payload["receipt_sha256"]


def test_bound_external_provenance_cli_rejects_pilot_policy_exact_byte_drift(
    tmp_path: Path,
) -> None:
    fixture = _bound_fixture(tmp_path)
    payload = json.loads(fixture["pilot_policy_path"].read_text(encoding="utf-8"))
    fixture["pilot_policy_path"].write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        fixture["args"], cwd=_root(), check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "different pilot-policy bytes" in result.stderr
    assert not fixture["output_path"].exists()


def test_bound_external_provenance_cli_rejects_attestation_exact_byte_drift(
    tmp_path: Path,
) -> None:
    fixture = _bound_fixture(tmp_path)
    threshold_id, path = next(iter(fixture["test_attestations"].items()))
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        fixture["args"], cwd=_root(), check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert threshold_id in result.stderr or "binding differs" in result.stderr
    assert not fixture["output_path"].exists()


def test_bound_external_provenance_cli_requires_both_release_bindings(tmp_path: Path) -> None:
    fixture = _bound_fixture(tmp_path)
    args = list(fixture["args"])
    index = args.index("--release-execution-binding")
    del args[index : index + 2]

    result = subprocess.run(
        args, cwd=_root(), check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "--release-execution-binding" in result.stderr
    assert not fixture["output_path"].exists()
