from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from veritas.benchmark import BenchmarkSplit
from veritas.extraction_benchmark import (
    build_extraction_selectivity_curve,
    evaluate_extraction_benchmark,
)
from veritas.extraction_calibration import (
    ExtractionThresholdObservation,
    select_development_threshold,
)
from veritas.extraction_calibration_archive import (
    ExtractionDevelopmentCalibrationFreeze,
    ExtractionDevelopmentCalibrationObservationArchive,
    development_calibration_freeze_json_payload,
    load_development_calibration_freeze,
    load_pretest_pilot_threshold_policy,
)
from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_evidence_workflow import (
    build_extraction_split_target_manifest,
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)
from veritas.extraction_execution_evidence import extraction_prediction_semantics_sha256
from veritas.extraction_release_archive import load_extraction_prediction_artifact
from veritas.extraction_review import build_extraction_gold_manifest
from veritas.extraction_review_record_json import load_extraction_review_record


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _prediction_paths(values: list[list[str]]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for threshold_id, path_text in values:
        if threshold_id in result:
            raise ValueError(f"duplicate DEVELOPMENT prediction threshold id: {threshold_id!r}")
        result[threshold_id] = Path(path_text)
    return result


def _validate_precommitted_inputs(plan, sampling_frame, seed_manifest) -> None:
    if sampling_frame.sha256() != plan.sampling_frame_sha256:
        raise ValueError("sampling frame does not match the precommitted evidence plan")
    if sampling_frame.source_manifest_sha256 != plan.sampling_frame_source_manifest_sha256:
        raise ValueError("sampling-frame source bytes do not match the precommitted evidence plan")
    if seed_manifest.source_manifest_sha256 != plan.source_seed_manifest_sha256:
        raise ValueError("seed-manifest source bytes do not match the precommitted evidence plan")
    if seed_manifest.sha256() != plan.seed_target_universe_sha256:
        raise ValueError("seed target universe does not match the precommitted evidence plan")


def _validate_reviewed_gold(gold_manifest, sampling_frame, seed_manifest) -> None:
    seed_targets = seed_manifest.target_map()
    family_by_paper = sampling_frame.paper_family_map()
    for target in gold_manifest.targets:
        seed_target = seed_targets.get(target.target_id)
        if seed_target is None:
            raise ValueError(
                "reviewed gold target is outside the precommitted seed target universe: "
                f"{target.target_id!r}"
            )
        seed_identity = (
            seed_target.paper_id,
            seed_target.article_family_id,
            seed_target.object_type,
            seed_target.key,
            seed_target.critical_for_hard_audit,
        )
        gold_identity = (
            target.paper_id,
            target.article_family_id,
            target.object_type,
            target.key,
            target.critical_for_hard_audit,
        )
        if seed_identity != gold_identity:
            raise ValueError(
                f"reviewed gold target identity drifted from seed manifest: {target.target_id!r}"
            )
        seed_locator = (
            seed_target.expected_page,
            seed_target.table_label,
            seed_target.row_label,
        )
        gold_locator = (
            target.source.page,
            target.source.table,
            target.source.row,
        )
        if seed_locator != gold_locator:
            raise ValueError(
                "reviewed gold source locator drifted from seed manifest: "
                f"{target.target_id!r}"
            )
        expected_family = family_by_paper.get(target.paper_id)
        if expected_family is None:
            raise ValueError(
                "reviewed gold paper is outside the precommitted sampling frame: "
                f"{target.paper_id!r}"
            )
        if expected_family != target.article_family_id:
            raise ValueError(
                f"reviewed gold article-family identity drifted: {target.target_id!r}"
            )


def _validate_prediction_membership(predictions, development_manifest) -> None:
    expected = set(development_manifest.target_ids)
    actual = {prediction.target_id for prediction in predictions}
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        extra = tuple(sorted(actual - expected))
        raise ValueError(
            "DEVELOPMENT prediction target membership differs from target manifest; "
            f"missing={missing!r}, extra={extra!r}"
        )


def _validate_prediction_threshold(predictions, *, threshold_id: str, threshold: float) -> None:
    drifted = tuple(
        sorted(
            prediction.target_id
            for prediction in predictions
            if float(prediction.resolution.calibration_threshold) != float(threshold)
        )
    )
    if drifted:
        raise ValueError(
            "DEVELOPMENT prediction calibration threshold differs from precommitted grid "
            f"for {threshold_id!r}: {drifted!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate only DEVELOPMENT prediction artifacts against independently adjudicated "
            "reviewed gold, select the threshold under the precommitted pilot policy, and write "
            "a strict non-production calibration freeze before TEST is opened."
        )
    )
    parser.add_argument("--sampling-frame", type=Path, required=True)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
    parser.add_argument("--pilot-threshold-policy", type=Path, required=True)
    parser.add_argument("--review-record", type=Path, action="append", required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument(
        "--development-prediction",
        nargs=2,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "PREDICTION_ARTIFACT"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sampling_frame = load_extraction_sampling_frame(args.sampling_frame)
    seed_manifest = load_extraction_seed_manifest(args.seed_manifest)
    plan, threshold_grid = load_extraction_evidence_plan(args.evidence_plan)
    _validate_precommitted_inputs(plan, sampling_frame, seed_manifest)

    pilot_policy = load_pretest_pilot_threshold_policy(args.pilot_threshold_policy)
    if pilot_policy.bound_evidence_plan_sha256 != plan.sha256():
        raise ValueError("pilot threshold policy is bound to a different evidence plan")
    if float(pilot_policy.benchmark_confidence) != float(plan.benchmark_confidence):
        raise ValueError("pilot threshold policy benchmark confidence differs from evidence plan")

    review_records = tuple(load_extraction_review_record(path) for path in args.review_record)
    target_ids = [record.target.target_id for record in review_records]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("review-record target ids must be unique")
    if any(record.adjudication is None for record in review_records):
        raise ValueError("DEVELOPMENT calibration review records require independent adjudication")

    gold_manifest = build_extraction_gold_manifest(
        review_records,
        split_salt=plan.split_salt,
        source_seed_manifest_sha256=plan.source_seed_manifest_sha256,
        review_protocol_version=plan.review_protocol_version,
    )
    _validate_reviewed_gold(gold_manifest, sampling_frame, seed_manifest)
    split_lock = gold_manifest.build_split_lock(
        train_fraction=plan.train_fraction,
        development_fraction=plan.development_fraction,
    )
    expected_development_manifest = build_extraction_split_target_manifest(
        gold_manifest,
        split_lock,
        split=BenchmarkSplit.DEVELOPMENT,
    )
    development_manifest = load_extraction_split_target_manifest(args.development_manifest)
    if development_manifest != expected_development_manifest:
        raise ValueError(
            "supplied DEVELOPMENT manifest differs from mechanically derived reviewed-gold split"
        )

    prediction_paths = _prediction_paths(args.development_prediction)
    grid = {threshold_id: float(threshold) for threshold_id, threshold in threshold_grid.points}
    if set(prediction_paths) != set(grid):
        missing = tuple(sorted(set(grid) - set(prediction_paths)))
        extra = tuple(sorted(set(prediction_paths) - set(grid)))
        raise ValueError(
            "DEVELOPMENT prediction artifacts differ from the complete precommitted threshold grid; "
            f"missing={missing!r}, extra={extra!r}"
        )

    development_target_ids = set(development_manifest.target_ids)
    development_gold = tuple(
        target for target in gold_manifest.targets if target.target_id in development_target_ids
    )
    if {target.target_id for target in development_gold} != development_target_ids:
        raise ValueError("DEVELOPMENT gold membership differs from target manifest")

    observations: list[ExtractionThresholdObservation] = []
    archived_observations: list[ExtractionDevelopmentCalibrationObservationArchive] = []
    for threshold_id in sorted(grid):
        threshold = grid[threshold_id]
        prediction_path = prediction_paths[threshold_id]
        if prediction_path.is_symlink() or not prediction_path.is_file():
            raise ValueError(
                f"DEVELOPMENT prediction artifact must be a regular non-symlink file: {prediction_path}"
            )
        predictions = load_extraction_prediction_artifact(prediction_path)
        _validate_prediction_membership(predictions, development_manifest)
        _validate_prediction_threshold(
            predictions,
            threshold_id=threshold_id,
            threshold=threshold,
        )
        report = evaluate_extraction_benchmark(
            development_gold,
            predictions,
            confidence=plan.benchmark_confidence,
        )
        observation = ExtractionThresholdObservation(
            threshold_id=threshold_id,
            threshold=threshold,
            split=BenchmarkSplit.DEVELOPMENT,
            report=report,
            predictions=predictions,
        )
        observations.append(observation)
        archived_observations.append(
            ExtractionDevelopmentCalibrationObservationArchive.from_report(
                threshold_id=threshold_id,
                threshold=threshold,
                prediction_artifact_sha256=_file_sha256(prediction_path),
                prediction_semantics_sha256=extraction_prediction_semantics_sha256(predictions),
                report=report,
            )
        )

    frozen_threshold = select_development_threshold(
        observations,
        policy=pilot_policy.threshold_policy,
        development_manifest_sha256=development_manifest.sha256(),
    )
    selectivity_curve = build_extraction_selectivity_curve(
        tuple((observation.threshold, observation.report) for observation in observations)
    )
    freeze = ExtractionDevelopmentCalibrationFreeze(
        evidence_plan_sha256=plan.sha256(),
        development_manifest_sha256=development_manifest.sha256(),
        benchmark_confidence=plan.benchmark_confidence,
        pilot_policy_file_sha256=pilot_policy.source_file_sha256,
        threshold_policy=pilot_policy.threshold_policy,
        observations=tuple(archived_observations),
        selectivity_curve=selectivity_curve,
        frozen_threshold=frozen_threshold,
    )

    payload = development_calibration_freeze_json_payload(freeze)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reloaded = load_development_calibration_freeze(args.output)
    if reloaded != freeze:
        raise ValueError("written DEVELOPMENT calibration freeze does not round-trip exactly")

    print(
        json.dumps(
            {
                "schema_version": 1,
                "production_authorized": False,
                "development_calibration_freeze_sha256": freeze.sha256(),
                "development_calibration_freeze_file_sha256": _file_sha256(args.output),
                "development_manifest_sha256": development_manifest.sha256(),
                "threshold_policy_sha256": pilot_policy.threshold_policy.sha256(),
                "frozen_threshold_sha256": frozen_threshold.sha256(),
                "selected_threshold_id": frozen_threshold.threshold_id,
                "selected_threshold": frozen_threshold.threshold,
                "candidate_threshold_ids": list(frozen_threshold.candidate_threshold_ids),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
