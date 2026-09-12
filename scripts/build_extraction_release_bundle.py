from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_calibration_archive import (
    load_development_calibration_freeze,
    load_pretest_pilot_threshold_policy,
    load_test_evaluation_archive,
)
from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
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
    label: str,
) -> tuple[ExtractionArchivedThresholdRun, ...]:
    seen: set[str] = set()
    runs: list[ExtractionArchivedThresholdRun] = []
    for threshold_id, execution_id, prediction_artifact_path in values:
        if threshold_id in seen:
            raise ValueError(f"duplicate {label} threshold id: {threshold_id!r}")
        seen.add(threshold_id)
        try:
            threshold = grid[threshold_id]
        except KeyError as exc:
            raise ValueError(
                f"{label} threshold id is outside the precommitted grid: {threshold_id!r}"
            ) from exc
        runs.append(
            ExtractionArchivedThresholdRun(
                threshold_id=threshold_id,
                threshold=threshold,
                execution_id=execution_id,
                prediction_artifact_path=prediction_artifact_path,
            )
        )
    if seen != set(grid):
        missing = tuple(sorted(set(grid) - seen))
        extra = tuple(sorted(seen - set(grid)))
        raise ValueError(
            f"{label} threshold runs differ from precommitted grid; "
            f"missing={missing!r}, extra={extra!r}"
        )
    return tuple(runs)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a canonical non-production extraction release-evidence bundle whose policy "
            "and threshold values are derived from the already frozen DEVELOPMENT/TEST chain, "
            "plus a strict sidecar binding the bundle to those exact calibration bytes."
        )
    )
    parser.add_argument("--review-record", type=Path, action="append", required=True)
    parser.add_argument("--release-artifact-root", type=Path, required=True)
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--input-artifact-root", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
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
        metavar=("THRESHOLD_ID", "EXECUTION_ID", "PREDICTION_ARTIFACT_PATH"),
    )
    parser.add_argument(
        "--test-run",
        nargs=3,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "EXECUTION_ID", "PREDICTION_ARTIFACT_PATH"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibration-binding-output", type=Path, required=True)
    args = parser.parse_args()

    review_records = tuple(load_extraction_review_record(path) for path in args.review_record)
    target_ids = [record.target.target_id for record in review_records]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("review-record target ids must be unique")
    if any(record.adjudication is None for record in review_records):
        raise ValueError("release bundle review records require independent adjudication")

    plan, threshold_grid = load_extraction_evidence_plan(args.evidence_plan)
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

    bundle = ExtractionReleaseEvidenceBundle(
        review_records=review_records,
        threshold_policy=development_freeze.threshold_policy,
        development_runs=_runs(
            args.development_run,
            grid=grid,
            label="DEVELOPMENT",
        ),
        test_runs=_runs(
            args.test_run,
            grid=grid,
            label="TEST",
        ),
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

    binding = build_extraction_release_calibration_binding(
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
            extraction_release_calibration_binding_json_payload(binding),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    reloaded_binding = load_extraction_release_calibration_binding(
        args.calibration_binding_output
    )
    if reloaded_binding != binding:
        raise ValueError("written release calibration binding does not round-trip exactly")

    print(
        json.dumps(
            {
                "schema_version": 1,
                "production_authorized": False,
                "release_bundle_sha256": bundle.sha256(),
                "release_bundle_file_sha256": _file_sha256(args.output),
                "release_calibration_binding_sha256": binding.sha256(),
                "release_calibration_binding_file_sha256": _file_sha256(
                    args.calibration_binding_output
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
