from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.extraction_calibration import ExtractionThresholdPolicy
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
from veritas.extraction_release_source_binding import (
    verify_extraction_release_source_artifacts,
)
from veritas.extraction_review_record_json import load_extraction_review_record


def _run(value: list[str], *, label: str) -> ExtractionArchivedThresholdRun:
    threshold_id, threshold_text, execution_id, prediction_artifact_path = value
    try:
        threshold = float(threshold_text)
    except ValueError as exc:
        raise ValueError(f"{label} threshold must be numeric") from exc
    return ExtractionArchivedThresholdRun(
        threshold_id=threshold_id,
        threshold=threshold,
        execution_id=execution_id,
        prediction_artifact_path=prediction_artifact_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a canonical non-production extraction release-evidence bundle from "
            "independently archived review records and DEV/TEST prediction artifacts."
        )
    )
    parser.add_argument("--review-record", type=Path, action="append", required=True)
    parser.add_argument("--release-artifact-root", type=Path, required=True)
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--input-artifact-root", type=Path, required=True)
    parser.add_argument(
        "--development-run",
        nargs=4,
        action="append",
        required=True,
        metavar=(
            "THRESHOLD_ID",
            "THRESHOLD",
            "EXECUTION_ID",
            "PREDICTION_ARTIFACT_PATH",
        ),
    )
    parser.add_argument(
        "--test-run",
        nargs=4,
        action="append",
        required=True,
        metavar=(
            "THRESHOLD_ID",
            "THRESHOLD",
            "EXECUTION_ID",
            "PREDICTION_ARTIFACT_PATH",
        ),
    )
    parser.add_argument("--min-selective-coverage", type=float, required=True)
    parser.add_argument("--min-accepted-full-accuracy", type=float, required=True)
    parser.add_argument(
        "--max-critical-family-wrong-accept-upper-bound",
        type=float,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    review_records = tuple(load_extraction_review_record(path) for path in args.review_record)
    target_ids = [record.target.target_id for record in review_records]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("review-record target ids must be unique")
    if any(record.adjudication is None for record in review_records):
        raise ValueError("release bundle review records require independent adjudication")

    policy = ExtractionThresholdPolicy(
        min_selective_coverage=args.min_selective_coverage,
        min_accepted_full_accuracy=args.min_accepted_full_accuracy,
        max_critical_family_wrong_accept_upper_bound=(
            args.max_critical_family_wrong_accept_upper_bound
        ),
    )
    bundle = ExtractionReleaseEvidenceBundle(
        review_records=review_records,
        threshold_policy=policy,
        development_runs=tuple(
            _run(value, label="DEVELOPMENT run") for value in args.development_run
        ),
        test_runs=tuple(_run(value, label="TEST run") for value in args.test_run),
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
    print(bundle.sha256())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
