from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from hashlib import sha256

from .benchmark import BenchmarkSplit
from .corpus import ArticleFamilySplitLock
from .extraction_benchmark import ExtractionPrediction, ExtractionSelectivityCurve
from .extraction_calibration import (
    ExtractionTestEvaluationLock,
    ExtractionThresholdObservation,
    ExtractionThresholdPolicy,
    FrozenExtractionThreshold,
)
from .extraction_evidence_workflow import (
    ExtractionEvidencePlan,
    ExtractionSamplingFrame,
    ExtractionSeedManifest,
    ExtractionThresholdGrid,
    build_extraction_evidence_release_receipt,
    build_extraction_split_target_manifest,
)
from .extraction_review import ExtractionGoldManifest, ExtractionReviewRecord
from .extraction_test_seal import ExtractionTestSetSeal

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExtractionExecutionPlan:
    input_artifact_manifest_sha256: str
    source_tree_sha256: str
    parser_registry_sha256: str
    numerical_runtime_sha256: str
    execution_command_sha256: str
    network_disabled: bool = True
    source_mount_read_only: bool = True
    credentials_mounted: bool = False
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("input_artifact_manifest_sha256", self.input_artifact_manifest_sha256),
            ("source_tree_sha256", self.source_tree_sha256),
            ("parser_registry_sha256", self.parser_registry_sha256),
            ("numerical_runtime_sha256", self.numerical_runtime_sha256),
            ("execution_command_sha256", self.execution_command_sha256),
        ):
            _require_sha256(value, label=label)
        _require_bool(self.network_disabled, label="network_disabled")
        _require_bool(self.source_mount_read_only, label="source_mount_read_only")
        _require_bool(self.credentials_mounted, label="credentials_mounted")
        _require_bool(self.production_authorized, label="production_authorized")
        if not self.network_disabled:
            raise ValueError("extraction evidence execution must disable network access")
        if not self.source_mount_read_only:
            raise ValueError("extraction evidence source mount must be read-only")
        if self.credentials_mounted:
            raise ValueError("extraction evidence execution must not mount credentials")
        if self.production_authorized:
            raise ValueError("extraction execution plans are non-production only")
        _require_schema_version(self.schema_version, label="extraction execution plan")

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class ExtractionExecutionAttestation:
    execution_id: str
    execution_plan_sha256: str
    split: BenchmarkSplit
    threshold_id: str
    threshold: float
    target_manifest_sha256: str
    prediction_artifact_sha256: str
    prediction_semantics_sha256: str
    exit_code: int = 0
    network_disabled: bool = True
    source_mount_read_only: bool = True
    credentials_mounted: bool = False
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_nonempty_string(self.execution_id, label="execution_id")
        _require_nonempty_string(self.threshold_id, label="threshold_id")
        for label, value in (
            ("execution_plan_sha256", self.execution_plan_sha256),
            ("target_manifest_sha256", self.target_manifest_sha256),
            ("prediction_artifact_sha256", self.prediction_artifact_sha256),
            ("prediction_semantics_sha256", self.prediction_semantics_sha256),
        ):
            _require_sha256(value, label=label)
        if not isinstance(self.split, BenchmarkSplit):
            raise TypeError("execution attestation split must be a BenchmarkSplit")
        if self.split not in {BenchmarkSplit.DEVELOPMENT, BenchmarkSplit.TEST}:
            raise ValueError("execution attestation split must be DEVELOPMENT or TEST")
        _require_finite_nonnegative_number(self.threshold, label="threshold")
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise TypeError("execution attestation exit_code must be an integer")
        if self.exit_code != 0:
            raise ValueError("extraction evidence execution must exit successfully")
        _require_bool(self.network_disabled, label="network_disabled")
        _require_bool(self.source_mount_read_only, label="source_mount_read_only")
        _require_bool(self.credentials_mounted, label="credentials_mounted")
        _require_bool(self.production_authorized, label="production_authorized")
        if not self.network_disabled:
            raise ValueError("extraction evidence execution must attest disabled network")
        if not self.source_mount_read_only:
            raise ValueError("extraction evidence execution must attest a read-only source mount")
        if self.credentials_mounted:
            raise ValueError("extraction evidence execution must attest no mounted credentials")
        if self.production_authorized:
            raise ValueError("extraction execution attestations are non-production only")
        _require_schema_version(self.schema_version, label="extraction execution attestation")

    def sha256(self) -> str:
        payload = asdict(self)
        payload["split"] = self.split.value
        return _stable_sha256(payload)


@dataclass(frozen=True)
class ExtractionExecutionEvidence:
    attestation: ExtractionExecutionAttestation
    prediction_artifact: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.attestation, ExtractionExecutionAttestation):
            raise TypeError("attestation must be an ExtractionExecutionAttestation")
        if not isinstance(self.prediction_artifact, bytes):
            raise TypeError("prediction_artifact must contain exact bytes")
        artifact_sha256 = sha256(self.prediction_artifact).hexdigest()
        if artifact_sha256 != self.attestation.prediction_artifact_sha256:
            raise ValueError("prediction artifact bytes do not match execution attestation")

    def sha256(self) -> str:
        return _stable_sha256(
            {
                "attestation_sha256": self.attestation.sha256(),
                "prediction_artifact_sha256": sha256(self.prediction_artifact).hexdigest(),
            }
        )


@dataclass(frozen=True)
class AttestedExtractionEvidenceReleaseReceipt:
    base_release_receipt_sha256: str
    evidence_plan_sha256: str
    execution_plan_sha256: str
    development_execution_set_sha256: str
    test_execution_set_sha256: str
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("base_release_receipt_sha256", self.base_release_receipt_sha256),
            ("evidence_plan_sha256", self.evidence_plan_sha256),
            ("execution_plan_sha256", self.execution_plan_sha256),
            ("development_execution_set_sha256", self.development_execution_set_sha256),
            ("test_execution_set_sha256", self.test_execution_set_sha256),
        ):
            _require_sha256(value, label=label)
        _require_bool(self.production_authorized, label="production_authorized")
        if self.production_authorized:
            raise ValueError("attested extraction release receipts are non-production only")
        _require_schema_version(
            self.schema_version,
            label="attested extraction evidence release receipt",
        )

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


def extraction_prediction_artifact_bytes(
    predictions: tuple[ExtractionPrediction, ...] | list[ExtractionPrediction],
) -> bytes:
    predictions = _validated_predictions(predictions)
    payload = {
        "schema_version": 1,
        "predictions": [asdict(prediction) for prediction in predictions],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def extraction_prediction_semantics_sha256(
    predictions: tuple[ExtractionPrediction, ...] | list[ExtractionPrediction],
) -> str:
    predictions = _validated_predictions(predictions)
    return _stable_sha256(
        {
            "predictions": [
                asdict(prediction)
                for prediction in sorted(predictions, key=lambda item: item.target_id)
            ]
        }
    )


def build_extraction_execution_evidence(
    *,
    plan: ExtractionExecutionPlan,
    execution_id: str,
    split: BenchmarkSplit,
    threshold_id: str,
    threshold: float,
    target_manifest_sha256: str,
    predictions: tuple[ExtractionPrediction, ...] | list[ExtractionPrediction],
    prediction_artifact: bytes,
) -> ExtractionExecutionEvidence:
    if not isinstance(plan, ExtractionExecutionPlan):
        raise TypeError("plan must be an ExtractionExecutionPlan")
    predictions = _validated_predictions(predictions)
    canonical_artifact = extraction_prediction_artifact_bytes(predictions)
    if prediction_artifact != canonical_artifact:
        raise ValueError(
            "prediction artifact must use the canonical extraction prediction JSON contract"
        )
    attestation = ExtractionExecutionAttestation(
        execution_id=execution_id,
        execution_plan_sha256=plan.sha256(),
        split=split,
        threshold_id=threshold_id,
        threshold=threshold,
        target_manifest_sha256=target_manifest_sha256,
        prediction_artifact_sha256=sha256(prediction_artifact).hexdigest(),
        prediction_semantics_sha256=extraction_prediction_semantics_sha256(predictions),
    )
    return ExtractionExecutionEvidence(
        attestation=attestation,
        prediction_artifact=prediction_artifact,
    )


def build_attested_extraction_evidence_release_receipt(
    *,
    execution_plan: ExtractionExecutionPlan,
    development_execution_evidence: tuple[ExtractionExecutionEvidence, ...]
    | list[ExtractionExecutionEvidence],
    test_execution_evidence: tuple[ExtractionExecutionEvidence, ...]
    | list[ExtractionExecutionEvidence],
    plan: ExtractionEvidencePlan,
    sampling_frame: ExtractionSamplingFrame,
    seed_manifest: ExtractionSeedManifest,
    threshold_grid: ExtractionThresholdGrid,
    gold_manifest: ExtractionGoldManifest,
    review_records: tuple[ExtractionReviewRecord, ...] | list[ExtractionReviewRecord],
    split_lock: ArticleFamilySplitLock,
    threshold_policy: ExtractionThresholdPolicy,
    development_observations: tuple[ExtractionThresholdObservation, ...]
    | list[ExtractionThresholdObservation],
    test_observations: tuple[ExtractionThresholdObservation, ...]
    | list[ExtractionThresholdObservation],
    frozen_threshold: FrozenExtractionThreshold,
    test_seal: ExtractionTestSetSeal,
    test_evaluation_lock: ExtractionTestEvaluationLock,
    development_curve: ExtractionSelectivityCurve,
    test_curve: ExtractionSelectivityCurve,
) -> AttestedExtractionEvidenceReleaseReceipt:
    if not isinstance(execution_plan, ExtractionExecutionPlan):
        raise TypeError("execution_plan must be an ExtractionExecutionPlan")

    base_receipt = build_extraction_evidence_release_receipt(
        plan=plan,
        sampling_frame=sampling_frame,
        seed_manifest=seed_manifest,
        threshold_grid=threshold_grid,
        gold_manifest=gold_manifest,
        review_records=review_records,
        split_lock=split_lock,
        threshold_policy=threshold_policy,
        development_observations=development_observations,
        test_observations=test_observations,
        frozen_threshold=frozen_threshold,
        test_seal=test_seal,
        test_evaluation_lock=test_evaluation_lock,
        development_curve=development_curve,
        test_curve=test_curve,
    )

    development_manifest = build_extraction_split_target_manifest(
        gold_manifest,
        split_lock,
        split=BenchmarkSplit.DEVELOPMENT,
    )
    test_manifest = build_extraction_split_target_manifest(
        gold_manifest,
        split_lock,
        split=BenchmarkSplit.TEST,
    )
    development_execution_evidence = _validate_execution_evidence_set(
        development_execution_evidence,
        tuple(development_observations),
        execution_plan=execution_plan,
        split=BenchmarkSplit.DEVELOPMENT,
        target_manifest_sha256=development_manifest.sha256(),
        label="DEVELOPMENT",
    )
    test_execution_evidence = _validate_execution_evidence_set(
        test_execution_evidence,
        tuple(test_observations),
        execution_plan=execution_plan,
        split=BenchmarkSplit.TEST,
        target_manifest_sha256=test_manifest.sha256(),
        label="TEST",
    )
    return AttestedExtractionEvidenceReleaseReceipt(
        base_release_receipt_sha256=base_receipt.sha256(),
        evidence_plan_sha256=base_receipt.plan_sha256,
        execution_plan_sha256=execution_plan.sha256(),
        development_execution_set_sha256=_execution_evidence_set_sha256(
            development_execution_evidence
        ),
        test_execution_set_sha256=_execution_evidence_set_sha256(test_execution_evidence),
    )


def _validate_execution_evidence_set(
    evidence: tuple[ExtractionExecutionEvidence, ...] | list[ExtractionExecutionEvidence],
    observations: tuple[ExtractionThresholdObservation, ...],
    *,
    execution_plan: ExtractionExecutionPlan,
    split: BenchmarkSplit,
    target_manifest_sha256: str,
    label: str,
) -> tuple[ExtractionExecutionEvidence, ...]:
    evidence = tuple(evidence)
    if not evidence:
        raise ValueError(f"attested release requires {label} execution evidence")
    if any(not isinstance(item, ExtractionExecutionEvidence) for item in evidence):
        raise TypeError(f"{label} execution evidence contains an unsupported value")

    by_threshold = {item.attestation.threshold_id: item for item in evidence}
    if len(by_threshold) != len(evidence):
        raise ValueError(f"{label} execution evidence threshold ids must be unique")
    observation_by_threshold = {
        observation.threshold_id: observation for observation in observations
    }
    if set(by_threshold) != set(observation_by_threshold):
        raise ValueError(f"{label} execution evidence differs from threshold observation membership")

    for threshold_id in sorted(observation_by_threshold):
        observation = observation_by_threshold[threshold_id]
        item = by_threshold[threshold_id]
        attestation = item.attestation
        if observation.predictions is None:
            raise ValueError(f"{label} observation lacks prediction provenance")
        if attestation.execution_plan_sha256 != execution_plan.sha256():
            raise ValueError(f"{label} execution attestation uses a different execution plan")
        if attestation.split is not split:
            raise ValueError(f"{label} execution attestation uses the wrong split")
        if float(attestation.threshold) != float(observation.threshold):
            raise ValueError(f"{label} execution attestation threshold value differs")
        if attestation.target_manifest_sha256 != target_manifest_sha256:
            raise ValueError(f"{label} execution attestation uses a different target manifest")
        canonical_artifact = extraction_prediction_artifact_bytes(observation.predictions)
        if item.prediction_artifact != canonical_artifact:
            raise ValueError(f"{label} execution artifact differs from bound prediction provenance")
        expected_semantics = extraction_prediction_semantics_sha256(observation.predictions)
        if attestation.prediction_semantics_sha256 != expected_semantics:
            raise ValueError(f"{label} execution attestation prediction semantics differ")

    execution_ids = [item.attestation.execution_id for item in evidence]
    if len(set(execution_ids)) != len(execution_ids):
        raise ValueError(f"{label} execution ids must be unique per threshold")
    return evidence


def _execution_evidence_set_sha256(
    evidence: tuple[ExtractionExecutionEvidence, ...],
) -> str:
    return _stable_sha256(
        {
            "executions": [
                {
                    "threshold_id": item.attestation.threshold_id,
                    "evidence_sha256": item.sha256(),
                }
                for item in sorted(evidence, key=lambda value: value.attestation.threshold_id)
            ]
        }
    )


def _validated_predictions(
    predictions: tuple[ExtractionPrediction, ...] | list[ExtractionPrediction],
) -> tuple[ExtractionPrediction, ...]:
    predictions = tuple(predictions)
    if any(not isinstance(prediction, ExtractionPrediction) for prediction in predictions):
        raise TypeError("predictions must contain ExtractionPrediction values")
    target_ids = [prediction.target_id for prediction in predictions]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("prediction target_id values must be unique")
    return predictions


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_finite_nonnegative_number(value: object, *, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{label} must be a finite non-negative number")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_bool(value: object, *, label: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{label} must be boolean")


def _require_schema_version(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} schema_version must be integer 1")
    if value != 1:
        raise ValueError(f"{label} schema_version must be integer 1")


def _stable_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()