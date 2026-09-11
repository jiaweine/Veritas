from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from hashlib import sha256

from .benchmark import BenchmarkSplit
from .extraction_benchmark import ExtractionBenchmarkReport, ExtractionPrediction

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExtractionThresholdObservation:
    threshold_id: str
    threshold: float
    split: BenchmarkSplit
    report: ExtractionBenchmarkReport
    predictions: tuple[ExtractionPrediction, ...] | None = None

    def __post_init__(self) -> None:
        _require_nonempty_string(self.threshold_id, label="threshold_id")
        _require_finite_nonnegative_number(self.threshold, label="threshold")
        if not isinstance(self.split, BenchmarkSplit):
            raise TypeError("split must be a BenchmarkSplit")
        if not isinstance(self.report, ExtractionBenchmarkReport):
            raise TypeError("report must be an ExtractionBenchmarkReport")
        if self.predictions is not None:
            if not isinstance(self.predictions, tuple):
                raise TypeError("predictions must be a tuple of ExtractionPrediction values or None")
            if any(not isinstance(prediction, ExtractionPrediction) for prediction in self.predictions):
                raise TypeError("predictions must contain ExtractionPrediction values")
            target_ids = [prediction.target_id for prediction in self.predictions]
            if len(set(target_ids)) != len(target_ids):
                raise ValueError("prediction target_id values must be unique within an observation")


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
            _require_probability(value, label=name)
        _require_schema_version(self.schema_version, label="extraction threshold policy")

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
    policy_sha256: str
    candidate_threshold_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_nonempty_string(self.threshold_id, label="threshold_id")
        _require_finite_nonnegative_number(self.threshold, label="threshold")
        _require_sha256(self.development_manifest_sha256, label="development_manifest_sha256")
        _require_sha256(self.policy_sha256, label="policy_sha256")
        if not isinstance(self.candidate_threshold_ids, tuple) or not self.candidate_threshold_ids:
            raise ValueError("candidate_threshold_ids must be a non-empty tuple")
        for threshold_id in self.candidate_threshold_ids:
            _require_nonempty_string(threshold_id, label="candidate threshold id")
        if len(set(self.candidate_threshold_ids)) != len(self.candidate_threshold_ids):
            raise ValueError("candidate_threshold_ids must be unique")
        if self.threshold_id not in self.candidate_threshold_ids:
            raise ValueError("selected threshold_id must be present in candidate_threshold_ids")
        _require_schema_version(self.schema_version, label="frozen extraction threshold")

    def sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "threshold_id": self.threshold_id,
            "threshold": self.threshold,
            "development_manifest_sha256": self.development_manifest_sha256,
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
        _require_sha256(self.frozen_threshold_sha256, label="frozen_threshold_sha256")
        _require_sha256(self.test_manifest_sha256, label="test_manifest_sha256")
        _require_schema_version(self.schema_version, label="extraction TEST evaluation lock")

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


def select_development_threshold(
    observations: tuple[ExtractionThresholdObservation, ...] | list[ExtractionThresholdObservation],
    *,
    policy: ExtractionThresholdPolicy,
    development_manifest_sha256: str,
) -> FrozenExtractionThreshold:
    observations = tuple(observations)
    if not observations:
        raise ValueError("at least one threshold observation is required")
    if not isinstance(policy, ExtractionThresholdPolicy):
        raise TypeError("policy must be an ExtractionThresholdPolicy")
    _require_sha256(development_manifest_sha256, label="development_manifest_sha256")
    if any(not isinstance(observation, ExtractionThresholdObservation) for observation in observations):
        raise TypeError("observations must contain ExtractionThresholdObservation values")
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
            -observation.threshold,
            observation.threshold_id,
        ),
    )
    return FrozenExtractionThreshold(
        threshold_id=selected.threshold_id,
        threshold=selected.threshold,
        development_manifest_sha256=development_manifest_sha256,
        policy_sha256=policy.sha256(),
        candidate_threshold_ids=tuple(sorted(ids)),
    )


def lock_test_evaluation(
    frozen_threshold: FrozenExtractionThreshold,
    *,
    test_manifest_sha256: str,
) -> ExtractionTestEvaluationLock:
    """Bind TEST evaluation to a previously frozen DEVELOPMENT-selected threshold.

    This function intentionally accepts no TEST performance report and exposes no threshold
    selection logic. TEST results may evaluate a frozen threshold but may not influence it.
    """

    if not isinstance(frozen_threshold, FrozenExtractionThreshold):
        raise TypeError("frozen_threshold must be a FrozenExtractionThreshold")
    _require_sha256(test_manifest_sha256, label="test_manifest_sha256")
    return ExtractionTestEvaluationLock(
        frozen_threshold_sha256=frozen_threshold.sha256(),
        test_manifest_sha256=test_manifest_sha256,
    )


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


def _require_probability(value: object, *, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{label} must be a finite number in [0, 1]")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_schema_version(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != 1:
        raise ValueError(f"{label} schema_version must be 1")
