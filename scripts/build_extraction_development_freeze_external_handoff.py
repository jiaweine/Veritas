from __future__ import annotations

import argparse
import json
import re
from dataclasses import fields
from hashlib import sha256
from pathlib import Path
from typing import Any

from veritas.benchmark import BenchmarkSplit
from veritas.extraction_calibration_archive import (
    load_development_calibration_freeze,
    load_pretest_pilot_threshold_policy,
    load_test_evaluation_archive,
)
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_execution_evidence import extraction_prediction_semantics_sha256
from veritas.extraction_execution_evidence_json import load_extraction_execution_attestation
from veritas.extraction_pretest_archive_receipt import (
    VerifiedPretestExternalArchiveReceiptBinding,
)
from veritas.extraction_release_archive import load_extraction_prediction_artifact

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key is not allowed: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")


def _load_verified_initial_binding(path: Path) -> VerifiedPretestExternalArchiveReceiptBinding:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("initial archive binding must be UTF-8 JSON") from exc
    payload = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_object_keys,
        parse_constant=_reject_json_constant,
    )
    if not isinstance(payload, dict):
        raise TypeError("initial archive binding root must be an object")
    expected = {field.name for field in fields(VerifiedPretestExternalArchiveReceiptBinding)}
    actual = set(payload)
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        unknown = tuple(sorted(actual - expected))
        raise ValueError(
            "initial archive binding keys differ from schema; "
            f"missing={missing!r}, unknown={unknown!r}"
        )
    return VerifiedPretestExternalArchiveReceiptBinding(**payload)


def _path_map(values: list[list[str]], *, label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for threshold_id, path_text in values:
        if threshold_id in result:
            raise ValueError(f"duplicate {label} threshold id: {threshold_id!r}")
        path = Path(path_text)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} must be a regular non-symlink file: {path}")
        result[threshold_id] = path
    return result


def _repository_file(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"archive handoff input must be a regular non-symlink file: {path}")
    return {"path": path.as_posix(), "sha256": _file_sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a post-DEVELOPMENT / pre-TEST external-archive handoff that binds the "
            "historically frozen DEVELOPMENT decision, TEST evaluation lock, exact DEVELOPMENT "
            "prediction bytes, and per-threshold execution attestations. This is a repository-side "
            "handoff only; an independently controlled historical archive must still issue the receipt."
        )
    )
    parser.add_argument("--source-commit-sha", required=True)
    parser.add_argument("--initial-archive-binding", type=Path, required=True)
    parser.add_argument("--pilot-threshold-policy", type=Path, required=True)
    parser.add_argument("--development-freeze", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--test-evaluation-lock", type=Path, required=True)
    parser.add_argument("--test-manifest", type=Path, required=True)
    parser.add_argument(
        "--development-prediction",
        nargs=2,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "PREDICTION_ARTIFACT"),
    )
    parser.add_argument(
        "--development-attestation",
        nargs=2,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "ATTESTATION_JSON"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not _GIT_SHA_RE.fullmatch(args.source_commit_sha):
        raise ValueError("source commit SHA must be 40 lowercase hexadecimal characters")

    initial_binding = _load_verified_initial_binding(args.initial_archive_binding)
    if initial_binding.source_commit_sha != args.source_commit_sha:
        raise ValueError("initial archive binding is bound to a different source commit")

    freeze = load_development_calibration_freeze(args.development_freeze)
    pilot_policy = load_pretest_pilot_threshold_policy(args.pilot_threshold_policy)
    development_manifest = load_extraction_split_target_manifest(args.development_manifest)
    test_archive = load_test_evaluation_archive(args.test_evaluation_lock)
    test_manifest = load_extraction_split_target_manifest(args.test_manifest)

    if development_manifest.split is not BenchmarkSplit.DEVELOPMENT:
        raise ValueError("development manifest must use the DEVELOPMENT split")
    if test_manifest.split is not BenchmarkSplit.TEST:
        raise ValueError("test manifest must use the TEST split")
    if development_manifest.sha256() != freeze.development_manifest_sha256:
        raise ValueError("DEVELOPMENT manifest differs from the calibration freeze")
    if freeze.pilot_policy_file_sha256 != _file_sha256(args.pilot_threshold_policy):
        raise ValueError("pilot threshold policy bytes differ from the DEVELOPMENT freeze")
    if pilot_policy.bound_evidence_plan_sha256 != freeze.evidence_plan_sha256:
        raise ValueError("pilot threshold policy and DEVELOPMENT freeze use different evidence plans")
    if pilot_policy.threshold_policy.sha256() != freeze.threshold_policy.sha256():
        raise ValueError("pilot threshold policy differs from the DEVELOPMENT freeze")

    freeze_file_sha256 = _file_sha256(args.development_freeze)
    if test_archive.development_calibration_freeze_sha256 != freeze.sha256():
        raise ValueError("TEST evaluation archive uses a different DEVELOPMENT freeze")
    if test_archive.development_calibration_freeze_file_sha256 != freeze_file_sha256:
        raise ValueError("TEST evaluation archive uses different DEVELOPMENT freeze bytes")
    if test_archive.frozen_threshold_sha256 != freeze.frozen_threshold.sha256():
        raise ValueError("TEST evaluation archive uses a different frozen threshold")
    if test_archive.test_manifest_sha256 != test_manifest.sha256():
        raise ValueError("TEST evaluation archive uses a different TEST manifest")
    if test_archive.test_manifest_file_sha256 != _file_sha256(args.test_manifest):
        raise ValueError("TEST evaluation archive uses different TEST manifest bytes")
    if development_manifest.gold_manifest_sha256 != test_manifest.gold_manifest_sha256:
        raise ValueError("DEVELOPMENT and TEST manifests use different reviewed gold")
    if development_manifest.split_lock_sha256 != test_manifest.split_lock_sha256:
        raise ValueError("DEVELOPMENT and TEST manifests use different article-family split locks")

    expected_thresholds = {item.threshold_id: item for item in freeze.observations}
    prediction_paths = _path_map(
        args.development_prediction,
        label="DEVELOPMENT prediction artifact",
    )
    attestation_paths = _path_map(
        args.development_attestation,
        label="DEVELOPMENT execution attestation",
    )
    for label, actual in (
        ("prediction artifact", set(prediction_paths)),
        ("execution attestation", set(attestation_paths)),
    ):
        if actual != set(expected_thresholds):
            missing = tuple(sorted(set(expected_thresholds) - actual))
            extra = tuple(sorted(actual - set(expected_thresholds)))
            raise ValueError(
                f"DEVELOPMENT {label} membership differs from calibration freeze; "
                f"missing={missing!r}, extra={extra!r}"
            )

    threshold_rows: list[dict[str, object]] = []
    execution_ids: set[str] = set()
    expected_targets = set(development_manifest.target_ids)
    for threshold_id in sorted(expected_thresholds):
        archived = expected_thresholds[threshold_id]
        prediction_path = prediction_paths[threshold_id]
        prediction_file_sha256 = _file_sha256(prediction_path)
        if prediction_file_sha256 != archived.prediction_artifact_sha256:
            raise ValueError(
                f"DEVELOPMENT prediction bytes differ from calibration freeze: {threshold_id!r}"
            )
        predictions = load_extraction_prediction_artifact(prediction_path)
        if {prediction.target_id for prediction in predictions} != expected_targets:
            raise ValueError(
                f"DEVELOPMENT prediction membership differs from manifest: {threshold_id!r}"
            )
        prediction_semantics_sha256 = extraction_prediction_semantics_sha256(predictions)
        if prediction_semantics_sha256 != archived.prediction_semantics_sha256:
            raise ValueError(
                f"DEVELOPMENT prediction semantics differ from calibration freeze: {threshold_id!r}"
            )
        if any(
            float(prediction.resolution.calibration_threshold) != float(archived.threshold)
            for prediction in predictions
        ):
            raise ValueError(
                f"DEVELOPMENT prediction threshold differs from calibration freeze: {threshold_id!r}"
            )

        attestation_path = attestation_paths[threshold_id]
        attestation = load_extraction_execution_attestation(attestation_path)
        if attestation.split is not BenchmarkSplit.DEVELOPMENT:
            raise ValueError(
                f"DEVELOPMENT attestation uses the wrong split: {threshold_id!r}"
            )
        if attestation.threshold_id != threshold_id:
            raise ValueError(
                f"DEVELOPMENT attestation threshold id differs: {threshold_id!r}"
            )
        if float(attestation.threshold) != float(archived.threshold):
            raise ValueError(
                f"DEVELOPMENT attestation threshold value differs: {threshold_id!r}"
            )
        if attestation.target_manifest_sha256 != development_manifest.sha256():
            raise ValueError(
                f"DEVELOPMENT attestation uses a different target manifest: {threshold_id!r}"
            )
        if attestation.prediction_artifact_sha256 != prediction_file_sha256:
            raise ValueError(
                f"DEVELOPMENT attestation prediction bytes differ: {threshold_id!r}"
            )
        if attestation.prediction_semantics_sha256 != prediction_semantics_sha256:
            raise ValueError(
                f"DEVELOPMENT attestation prediction semantics differ: {threshold_id!r}"
            )
        if attestation.execution_id in execution_ids:
            raise ValueError("DEVELOPMENT execution ids must be unique across thresholds")
        execution_ids.add(attestation.execution_id)
        threshold_rows.append(
            {
                "threshold_id": threshold_id,
                "threshold": archived.threshold,
                "prediction_artifact_sha256": prediction_file_sha256,
                "prediction_semantics_sha256": prediction_semantics_sha256,
                "execution_id": attestation.execution_id,
                "attestation_sha256": attestation.sha256(),
                "attestation_file_sha256": _file_sha256(attestation_path),
            }
        )

    repository_paths = [
        args.initial_archive_binding,
        args.pilot_threshold_policy,
        args.development_freeze,
        args.development_manifest,
        args.test_evaluation_lock,
        args.test_manifest,
        *prediction_paths.values(),
        *attestation_paths.values(),
    ]
    path_strings = [path.as_posix() for path in repository_paths]
    if len(set(path_strings)) != len(path_strings):
        raise ValueError("external archive handoff input paths must be unique")
    repository_files = sorted(
        (_repository_file(path) for path in repository_paths),
        key=lambda row: row["path"],
    )

    payload = {
        "schema_version": 1,
        "status": "repository_side_external_archive_handoff_ready_awaiting_independent_archive",
        "production_authorized": False,
        "pretest_witness": {
            "path": args.test_evaluation_lock.as_posix(),
            "sha256": _file_sha256(args.test_evaluation_lock),
        },
        "source_commit_sha": args.source_commit_sha,
        "repository_files": repository_files,
        "required_external_binary_artifacts": {},
        "previous_pretest_archive_binding": {
            "binding_sha256": initial_binding.sha256(),
            "binding_file_sha256": _file_sha256(args.initial_archive_binding),
            "receipt_sha256": initial_binding.receipt_sha256,
            "receipt_file_sha256": initial_binding.receipt_file_sha256,
            "handoff_sha256": initial_binding.handoff_sha256,
            "archived_object_set_sha256": initial_binding.archived_object_set_sha256,
            "archive_channel_identity": initial_binding.archive_channel_identity,
            "archive_record_id": initial_binding.archive_record_id,
        },
        "development_calibration": {
            "freeze_sha256": freeze.sha256(),
            "freeze_file_sha256": freeze_file_sha256,
            "development_manifest_sha256": development_manifest.sha256(),
            "pilot_policy_file_sha256": freeze.pilot_policy_file_sha256,
            "frozen_threshold_sha256": freeze.frozen_threshold.sha256(),
            "selected_threshold_id": freeze.frozen_threshold.threshold_id,
            "selected_threshold": freeze.frozen_threshold.threshold,
        },
        "test_evaluation": {
            "archive_sha256": test_archive.sha256(),
            "archive_file_sha256": _file_sha256(args.test_evaluation_lock),
            "lock_sha256": test_archive.test_evaluation_lock.sha256(),
            "test_manifest_sha256": test_manifest.sha256(),
            "test_manifest_file_sha256": _file_sha256(args.test_manifest),
        },
        "development_executions": threshold_rows,
        "external_archive_requirements": {
            "preserve_exact_bytes": True,
            "independently_controlled_historical_channel_required": True,
            "immutable_or_append_only_record_required": True,
            "record_external_timestamp_or_sequence_position": True,
            "archive_before_any_test_prediction_is_opened": True,
            "independently_select_expected_context_before_test": True,
            "do_not_copy_expected_context_from_future_signed_envelope": True,
        },
        "pending_external_evidence": {
            "independent_archive_receipt_present": False,
            "independent_control_established": False,
            "historical_channel_semantics_established": False,
        },
        "executed_v015_development_predictions": True,
        "executed_v015_test_predictions": False,
        "note": (
            "This handoff is created after DEVELOPMENT calibration and before TEST execution. "
            "It binds exact repository-side freeze/lock/prediction/attestation bytes for later "
            "independent historical anchoring. It does not itself prove external control, historical "
            "timing, TEST untouchedness, key ownership, or production authority."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(_file_sha256(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
