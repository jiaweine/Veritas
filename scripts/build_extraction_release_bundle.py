from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from veritas.benchmark import BenchmarkSplit
from veritas.extraction_calibration_archive import (
    load_development_calibration_freeze,
    load_pretest_pilot_threshold_policy,
    load_test_evaluation_archive,
)
from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_execution_evidence_json import (
    load_extraction_execution_attestation,
    load_extraction_execution_plan,
)
from veritas.extraction_input_artifacts import (
    load_extraction_input_artifact_manifest,
    verify_extraction_input_artifact_manifest,
)
from veritas.extraction_release_archive import (
    ExtractionArchivedThresholdRun,
    ExtractionReleaseEvidenceBundle,
    extraction_release_evidence_bundle_payload,
    load_extraction_release_evidence_bundle,
)
from veritas.extraction_release_calibration_binding import (
    build_extraction_release_calibration_binding,
    extraction_release_calibration_binding_json_payload,
    load_extraction_release_calibration_binding,
)
from veritas.extraction_release_execution_binding import (
    build_extraction_release_execution_binding,
    extraction_release_execution_binding_json_payload,
    load_extraction_release_execution_binding,
)
from veritas.extraction_release_source_binding import (
    verify_extraction_release_source_artifacts,
)
from veritas.extraction_review_record_json import load_extraction_review_record


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _runs(
    values: list[list[str]],
    *,
    grid: dict[str, float],
    split: BenchmarkSplit,
    target_manifest_sha256: str,
    execution_plan_sha256: str,
    label: str,
) -> tuple[
    tuple[ExtractionArchivedThresholdRun, ...],
    dict[str, Path],
]:
    seen: set[str] = set()
    runs: list[ExtractionArchivedThresholdRun] = []
    attestations: dict[str, Path] = {}
    for threshold_id, prediction_artifact_path, attestation_path_text in values:
        if threshold_id in seen:
            raise ValueError(f"duplicate {label} threshold id: {threshold_id!r}")
        seen.add(threshold_id)
        try:
            threshold = grid[threshold_id]
        except KeyError as exc:
            raise ValueError(
                f"{label} threshold id is outside the precommitted grid: {threshold_id!r}"
            ) from exc
        attestation_path = Path(attestation_path_text)
        attestation = load_extraction_execution_attestation(attestation_path)
        if attestation.threshold_id != threshold_id:
            raise ValueError(f"{label} attestation threshold id differs from run threshold id")
        if float(attestation.threshold) != threshold:
            raise ValueError(f"{label} attestation threshold differs from precommitted grid")
        if attestation.split is not split:
            raise ValueError(f"{label} attestation uses the wrong split")
        if attestation.target_manifest_sha256 != target_manifest_sha256:
            raise ValueError(f"{label} attestation uses a different target manifest")
        if attestation.execution_plan_sha256 != execution_plan_sha256:
            raise ValueError(f"{label} attestation uses a different execution plan")
        runs.append(
            ExtractionArchivedThresholdRun(
                threshold_id=threshold_id,
                threshold=threshold,
                execution_id=attestation.execution_id,
                prediction_artifact_path=prediction_artifact_path,
            )
        )
        attestations[threshold_id] = attestation_path
    if seen != set(grid):
        missing = tuple(sorted(set(grid) - seen))
        extra = tuple(sorted(seen - set(grid)))
        raise ValueError(
            f"{label} threshold runs differ from precommitted grid; "
            f"missing={missing!r}, extra={extra!r}"
        )
    execution_ids = tuple(run.execution_id for run in runs)
    if len(set(execution_ids)) != len(execution_ids):
        raise ValueError(f"{label} execution ids must be unique per threshold")
    return tuple(runs), attestations


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a canonical non-production extraction release-evidence bundle whose policy, "
            "threshold values, and execution ids are derived from frozen calibration and strict "
            "per-threshold execution attestations, plus exact calibration/execution bindings."
        )
    )
    parser.add_argument("--review-record", type=Path, action="append", required=True)
    parser.add_argument("--release-artifact-root", type=Path, required=True)
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--input-artifact-root", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--pilot-threshold-policy", type=Path, required=True)
    parser.add_argument("--development-freeze", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--test-evaluation-lock", type=Path, required=True)
    parser.add_argument("--test-manifest", type=Path, required=True)
    parser.add_argument(
        "--development-run",
        nargs=3,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "PREDICTION_ARTIFACT_PATH", "EXECUTION_ATTESTATION"),
    )
    parser.add_argument(
        "--test-run",
        nargs=3,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "PREDICTION_ARTIFACT_PATH", "EXECUTION_ATTESTATION"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibration-binding-output", type=Path, required=True)
    parser.add_argument("--execution-binding-output", type=Path, required=True)
    args = parser.parse_args()

    review_records = tuple(load_extraction_review_record(path) for path in args.review_record)
    target_ids = [record.target.target_id for record in review_records]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("review-record target ids must be unique")
    if any(record.adjudication is None for record in review_records):
        raise ValueError("release bundle review records require independent adjudication")

    plan, threshold_grid = load_extraction_evidence_plan(args.evidence_plan)
    execution_plan = load_extraction_execution_plan(args.execution_plan)
    pilot_policy = load_pretest_pilot_threshold_policy(args.pilot_threshold_policy)
    development_freeze = load_development_calibration_freeze(args.development_freeze)
    development_manifest = load_extraction_split_target_manifest(args.development_manifest)
    test_evaluation_archive = load_test_evaluation_archive(args.test_evaluation_lock)
    test_manifest = load_extraction_split_target_manifest(args.test_manifest)

    grid = {
        threshold_id: float(threshold)
        for threshold_id, threshold in threshold_grid.points
    }
    frozen_grid = {
        observation.threshold_id: float(observation.threshold)
        for observation in development_freeze.observations
    }
    if frozen_grid != grid:
        raise ValueError("DEVELOPMENT freeze threshold grid differs from evidence plan")

    development_runs, development_attestations = _runs(
        args.development_run,
        grid=grid,
        split=BenchmarkSplit.DEVELOPMENT,
        target_manifest_sha256=development_manifest.sha256(),
        execution_plan_sha256=execution_plan.sha256(),
        label="DEVELOPMENT",
    )
    test_runs, test_attestations = _runs(
        args.test_run,
        grid=grid,
        split=BenchmarkSplit.TEST,
        target_manifest_sha256=test_manifest.sha256(),
        execution_plan_sha256=execution_plan.sha256(),
        label="TEST",
    )
    bundle = ExtractionReleaseEvidenceBundle(
        review_records=review_records,
        threshold_policy=development_freeze.threshold_policy,
        development_runs=development_runs,
        test_runs=test_runs,
    )

    input_manifest = load_extraction_input_artifact_manifest(args.input_artifact_manifest)
    verify_extraction_input_artifact_manifest(input_manifest, args.input_artifact_root)
    verify_extraction_release_source_artifacts(
        bundle,
        input_manifest,
        release_artifact_root=args.release_artifact_root,
    )

    payload = extraction_release_evidence_bundle_payload(bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reloaded = load_extraction_release_evidence_bundle(args.output)
    if reloaded != bundle:
        raise ValueError("written release evidence bundle does not round-trip exactly")

    calibration_binding = build_extraction_release_calibration_binding(
        bundle=bundle,
        bundle_path=args.output,
        plan=plan,
        threshold_grid_sha256=threshold_grid.sha256(),
        pilot_policy=pilot_policy,
        pilot_policy_path=args.pilot_threshold_policy,
        development_freeze=development_freeze,
        development_freeze_path=args.development_freeze,
        development_manifest=development_manifest,
        development_manifest_path=args.development_manifest,
        test_evaluation_archive=test_evaluation_archive,
        test_evaluation_archive_path=args.test_evaluation_lock,
        test_manifest=test_manifest,
        test_manifest_path=args.test_manifest,
        release_artifact_root=args.release_artifact_root,
    )
    args.calibration_binding_output.parent.mkdir(parents=True, exist_ok=True)
    args.calibration_binding_output.write_text(
        json.dumps(
            extraction_release_calibration_binding_json_payload(calibration_binding),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if load_extraction_release_calibration_binding(args.calibration_binding_output) != calibration_binding:
        raise ValueError("written release calibration binding does not round-trip exactly")

    execution_binding = build_extraction_release_execution_binding(
        bundle=bundle,
        bundle_path=args.output,
        execution_plan=execution_plan,
        execution_plan_path=args.execution_plan,
        development_manifest=development_manifest,
        test_manifest=test_manifest,
        release_artifact_root=args.release_artifact_root,
        development_attestation_paths=development_attestations,
        test_attestation_paths=test_attestations,
    )
    args.execution_binding_output.parent.mkdir(parents=True, exist_ok=True)
    args.execution_binding_output.write_text(
        json.dumps(
            extraction_release_execution_binding_json_payload(execution_binding),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if load_extraction_release_execution_binding(args.execution_binding_output) != execution_binding:
        raise ValueError("written release execution binding does not round-trip exactly")

    print(
        json.dumps(
            {
                "schema_version": 1,
                "production_authorized": False,
                "release_bundle_sha256": bundle.sha256(),
                "release_bundle_file_sha256": _file_sha256(args.output),
                "release_calibration_binding_sha256": calibration_binding.sha256(),
                "release_calibration_binding_file_sha256": _file_sha256(
                    args.calibration_binding_output
                ),
                "release_execution_binding_sha256": execution_binding.sha256(),
                "release_execution_binding_file_sha256": _file_sha256(
                    args.execution_binding_output
                ),
                "selected_threshold_id": development_freeze.frozen_threshold.threshold_id,
                "selected_threshold": development_freeze.frozen_threshold.threshold,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
