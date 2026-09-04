from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from hashlib import sha256
from typing import Any

from .benchmark import BenchmarkSplit
from .extraction_benchmark import (
    ExtractionBenchmarkReport,
    ExtractionPrediction,
    ExtractionSelectivityCurve,
    build_extraction_selectivity_curve,
    evaluate_extraction_benchmark,
)
from .extraction_split_manifest import ExtractionSplitManifest

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExtractionThresholdObservation:
    threshold_id: str
    threshold: float
    predictions: tuple[ExtractionPrediction, ...]
    manifest: ExtractionSplitManifest
    confidence: float = 0.95

    def __post_init__(self) -> None:
        if not isinstance(self.threshold_id, str) or not self.threshold_id.strip():
            raise ValueError("threshold_id is required")
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, (int, float))
            or not math.isfinite(float(self.threshold))
            or float(self.threshold) < 0.0
        ):
            raise ValueError("threshold must be a finite non-negative number")
        if not isinstance(self.manifest, ExtractionSplitManifest):
            raise TypeError("manifest must be an ExtractionSplitManifest")
        if not 0.0 < self.confidence < 1.0 or not math.isfinite(self.confidence):
            raise ValueError("confidence must be a finite value in (0, 1)")
        if any(not isinstance(prediction, ExtractionPrediction) for prediction in self.predictions):
            raise TypeError("predictions must contain ExtractionPrediction values")
        # Force validation now so duplicate/unknown target ids fail at construction rather than later.
        self.report
        self.prediction_set_sha256()

    @property
    def split(self) -> BenchmarkSplit:
        return self.manifest.split

    @property
    def manifest_sha256(self) -> str:
        return self.manifest.sha256()

    @property
    def report(self) -> ExtractionBenchmarkReport:
        return evaluate_extraction_benchmark(
            self.manifest.targets,
            self.predictions,
            confidence=self.confidence,
        )

    def prediction_set_sha256(self) -> str:
        payload = [
            _jsonable(asdict(prediction))
            for prediction in sorted(self.predictions, key=lambda item: item.target_id)
        ]
        return _stable_sha256(payload)


@dataclass(frozen=True)
class ExtractionSelectivityEvidence:
    """Canonical split manifest plus prediction-derived observations for one selectivity curve."""

    manifest: ExtractionSplitManifest
    observations: tuple[ExtractionThresholdObservation, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, ExtractionSplitManifest):
            raise TypeError("selectivity evidence manifest must be an ExtractionSplitManifest")
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise ValueError("selectivity evidence schema_version must be 1")
        if not self.observations:
            raise ValueError("selectivity evidence requires at least one threshold observation")
        wrong_manifest = [
            observation.threshold_id
            for observation in self.observations
            if observation.manifest.sha256() != self.manifest.sha256()
        ]
        if wrong_manifest:
            raise ValueError(
                "selectivity evidence observations must all use the declared split manifest: "
                f"{tuple(sorted(wrong_manifest))!r}"
            )
        ids = [observation.threshold_id for observation in self.observations]
        if len(set(ids)) != len(ids):
            raise ValueError("selectivity evidence threshold_id values must be unique")
        thresholds = [float(observation.threshold) for observation in self.observations]
        if len(set(thresholds)) != len(thresholds):
            raise ValueError("selectivity evidence threshold values must be unique")
        for observation in self.observations:
            self.manifest.validate_report_membership(observation.report)

    @property
    def split(self) -> BenchmarkSplit:
        return self.manifest.split

    @property
    def manifest_sha256(self) -> str:
        return self.manifest.sha256()

    def observation_set_sha256(self) -> str:
        return threshold_observations_sha256(self.observations)

    def curve(self) -> ExtractionSelectivityCurve:
        return build_extraction_selectivity_curve(
            tuple((float(observation.threshold), observation.report) for observation in self.observations)
        )

    def sha256(self) -> str:
        return _stable_sha256(
            {
                "schema_version": self.schema_version,
                "split": self.split.value,
                "manifest_sha256": self.manifest_sha256,
                "observation_set_sha256": self.observation_set_sha256(),
                "curve": [asdict(point) for point in self.curve().points],
            }
        )


@dataclass(frozen=True)
class ExtractionThresholdPolicy:
    min_selective_coverage: float = 0.25
    min_accepted_full_accuracy: float = 0.99
    max_critical_family_wrong_accept_upper_bound: float = 0.05
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name, value in (
            ("min_selective_coverage", self.min_selective_coverage),
            ("min_accepted_full_accuracy", self.min_accepted_full_accuracy),
            (
                "max_critical_family_wrong_accept_upper_bound",
                self.max_critical_family_wrong_accept_upper_bound,
            ),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

    def sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "min_selective_coverage": self.min_selective_coverage,
            "min_accepted_full_accuracy": self.min_accepted_full_accuracy,
            "max_critical_family_wrong_accept_upper_bound": (
                self.max_critical_family_wrong_accept_upper_bound
            ),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()


@dataclass(frozen=True)
class FrozenExtractionThreshold:
    threshold_id: str
    threshold: float
    development_manifest_sha256: str
    development_observation_set_sha256: str
    policy_sha256: str
    candidate_threshold_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.threshold_id.strip():
            raise ValueError("threshold_id is required")
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, (int, float))
            or not math.isfinite(float(self.threshold))
            or float(self.threshold) < 0.0
        ):
            raise ValueError("threshold must be a finite non-negative number")
        if not _SHA256_RE.fullmatch(self.development_manifest_sha256):
            raise ValueError("development_manifest_sha256 must be a lowercase SHA-256 digest")
        if not _SHA256_RE.fullmatch(self.development_observation_set_sha256):
            raise ValueError(
                "development_observation_set_sha256 must be a lowercase SHA-256 digest"
            )
        if not _SHA256_RE.fullmatch(self.policy_sha256):
            raise ValueError("policy_sha256 must be a lowercase SHA-256 digest")
        if not self.candidate_threshold_ids:
            raise ValueError("candidate_threshold_ids cannot be empty")

    def sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "threshold_id": self.threshold_id,
            "threshold": float(self.threshold),
            "development_manifest_sha256": self.development_manifest_sha256,
            "development_observation_set_sha256": self.development_observation_set_sha256,
            "policy_sha256": self.policy_sha256,
            "candidate_threshold_ids": sorted(self.candidate_threshold_ids),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()


@dataclass(frozen=True)
class ExtractionTestEvaluationLock:
    frozen_threshold_sha256: str
    test_manifest_sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.frozen_threshold_sha256):
            raise ValueError("frozen_threshold_sha256 must be a lowercase SHA-256 digest")
        if not _SHA256_RE.fullmatch(self.test_manifest_sha256):
            raise ValueError("test_manifest_sha256 must be a lowercase SHA-256 digest")

    def sha256(self) -> str:
        raw = json.dumps(
            {
                "schema_version": self.schema_version,
                "frozen_threshold_sha256": self.frozen_threshold_sha256,
                "test_manifest_sha256": self.test_manifest_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(raw).hexdigest()


def threshold_observations_sha256(
    observations: tuple[ExtractionThresholdObservation, ...] | list[ExtractionThresholdObservation],
) -> str:
    observations = tuple(observations)
    if not observations:
        raise ValueError("at least one threshold observation is required")
    ids = [observation.threshold_id for observation in observations]
    if len(set(ids)) != len(ids):
        raise ValueError("threshold_id values must be unique")
    payload = [
        {
            "threshold_id": observation.threshold_id,
            "threshold": float(observation.threshold),
            "split": observation.split.value,
            "manifest_sha256": observation.manifest_sha256,
            "confidence": observation.confidence,
            "prediction_set_sha256": observation.prediction_set_sha256(),
            "report": _report_payload(observation.report),
        }
        for observation in sorted(observations, key=lambda item: item.threshold_id)
    ]
    return _stable_sha256(payload)


def select_development_threshold(
    observations: tuple[ExtractionThresholdObservation, ...] | list[ExtractionThresholdObservation],
    *,
    policy: ExtractionThresholdPolicy,
    development_manifest: ExtractionSplitManifest,
) -> FrozenExtractionThreshold:
    observations = tuple(observations)
    if not observations:
        raise ValueError("at least one threshold observation is required")
    if not isinstance(development_manifest, ExtractionSplitManifest):
        raise TypeError("development_manifest must be an ExtractionSplitManifest")
    if development_manifest.split is not BenchmarkSplit.DEVELOPMENT:
        raise ValueError("threshold selection requires a DEVELOPMENT split manifest")
    non_development = [
        observation.threshold_id
        for observation in observations
        if observation.split is not BenchmarkSplit.DEVELOPMENT
    ]
    if non_development:
        raise ValueError(
            "threshold selection may use DEVELOPMENT observations only; "
            f"received non-development observations: {tuple(sorted(non_development))!r}"
        )
    wrong_manifest = [
        observation.threshold_id
        for observation in observations
        if observation.manifest_sha256 != development_manifest.sha256()
    ]
    if wrong_manifest:
        raise ValueError(
            "threshold selection observations are bound to a different DEVELOPMENT manifest: "
            f"{tuple(sorted(wrong_manifest))!r}"
        )
    ids = [observation.threshold_id for observation in observations]
    if len(set(ids)) != len(ids):
        raise ValueError("threshold_id values must be unique")

    eligible = [
        observation
        for observation in observations
        if observation.report.selective_coverage >= policy.min_selective_coverage
        and observation.report.accepted_full_accuracy >= policy.min_accepted_full_accuracy
        and observation.report.critical_family_wrong_accept_upper_bound
        <= policy.max_critical_family_wrong_accept_upper_bound
    ]
    if not eligible:
        raise ValueError("no DEVELOPMENT threshold satisfies the extraction calibration policy")

    selected = max(
        eligible,
        key=lambda observation: (
            observation.report.selective_coverage,
            observation.report.accepted_full_accuracy,
            -observation.report.critical_family_wrong_accept_upper_bound,
            -float(observation.threshold),
            observation.threshold_id,
        ),
    )
    return FrozenExtractionThreshold(
        threshold_id=selected.threshold_id,
        threshold=float(selected.threshold),
        development_manifest_sha256=development_manifest.sha256(),
        development_observation_set_sha256=threshold_observations_sha256(observations),
        policy_sha256=policy.sha256(),
        candidate_threshold_ids=tuple(sorted(ids)),
    )


def lock_test_evaluation(
    frozen_threshold: FrozenExtractionThreshold,
    *,
    test_manifest: ExtractionSplitManifest,
) -> ExtractionTestEvaluationLock:
    """Bind TEST evaluation to a canonical TEST manifest and a frozen DEVELOPMENT threshold."""

    if not isinstance(test_manifest, ExtractionSplitManifest):
        raise TypeError("test_manifest must be an ExtractionSplitManifest")
    if test_manifest.split is not BenchmarkSplit.TEST:
        raise ValueError("TEST evaluation lock requires a TEST split manifest")
    return ExtractionTestEvaluationLock(
        frozen_threshold_sha256=frozen_threshold.sha256(),
        test_manifest_sha256=test_manifest.sha256(),
    )


def _report_payload(report: ExtractionBenchmarkReport) -> dict[str, Any]:
    payload = asdict(report)
    outcomes = payload.get("outcomes", [])
    payload["outcomes"] = sorted(outcomes, key=lambda item: item["target_id"])
    return _jsonable(payload)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _stable_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()
