from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_execution_evidence import build_extraction_execution_evidence
from veritas.extraction_execution_evidence_json import (
    extraction_execution_attestation_json_payload,
    load_extraction_execution_attestation,
    load_extraction_execution_plan,
)
from veritas.extraction_release_archive import load_extraction_prediction_artifact


def _precommitted_threshold(threshold_grid, threshold_id: str) -> float:
    by_id = {candidate_id: float(value) for candidate_id, value in threshold_grid.points}
    if threshold_id not in by_id:
        raise ValueError(f"threshold_id is not present in the precommitted grid: {threshold_id!r}")
    return by_id[threshold_id]


def _require_exact_target_membership(target_manifest, predictions) -> None:
    expected = set(target_manifest.target_ids)
    actual = {prediction.target_id for prediction in predictions}
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        extra = tuple(sorted(actual - expected))
        raise ValueError(
            "prediction artifact target membership differs from target manifest; "
            f"missing={missing!r}, extra={extra!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a strict non-production execution-attestation archive from an exact canonical "
            "prediction artifact, derived split manifest, precommitted threshold grid, and execution plan."
        )
    )
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
    parser.add_argument("--target-manifest", type=Path, required=True)
    parser.add_argument("--prediction-artifact", type=Path, required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--threshold-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    execution_plan = load_extraction_execution_plan(args.execution_plan)
    _, threshold_grid = load_extraction_evidence_plan(args.evidence_plan)
    target_manifest = load_extraction_split_target_manifest(args.target_manifest)
    predictions = load_extraction_prediction_artifact(args.prediction_artifact)
    _require_exact_target_membership(target_manifest, predictions)

    threshold = _precommitted_threshold(threshold_grid, args.threshold_id)
    prediction_artifact = args.prediction_artifact.read_bytes()
    execution_evidence = build_extraction_execution_evidence(
        plan=execution_plan,
        execution_id=args.execution_id,
        split=target_manifest.split,
        threshold_id=args.threshold_id,
        threshold=threshold,
        target_manifest_sha256=target_manifest.sha256(),
        predictions=predictions,
        prediction_artifact=prediction_artifact,
    )
    attestation = execution_evidence.attestation

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            extraction_execution_attestation_json_payload(attestation),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if load_extraction_execution_attestation(args.output) != attestation:
        raise ValueError("written execution attestation does not strict-round-trip exactly")

    result = {
        "attestation_sha256": attestation.sha256(),
        "attestation_file_sha256": sha256(args.output.read_bytes()).hexdigest(),
        "execution_id": attestation.execution_id,
        "execution_plan_sha256": attestation.execution_plan_sha256,
        "split": attestation.split.value,
        "threshold_id": attestation.threshold_id,
        "threshold": attestation.threshold,
        "target_manifest_sha256": attestation.target_manifest_sha256,
        "prediction_artifact_sha256": attestation.prediction_artifact_sha256,
        "prediction_semantics_sha256": attestation.prediction_semantics_sha256,
        "production_authorized": attestation.production_authorized,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
