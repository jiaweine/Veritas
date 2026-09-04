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
    ExtractionSelectivityCurve,
    build_extraction_selectivity_curve,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExtractionThresholdObservation:
    threshold_id: str
    threshold: float
    split: BenchmarkSplit
    report: ExtractionBenchmarkReport
    manifest_sha256: str

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
        if not isinstance(self.split, BenchmarkSplit):
            raise TypeError("split must be a BenchmarkSplit")
        if not isinstance(self.report, ExtractionBenchmarkReport):
            raise TypeError("report must be an ExtractionBenchmarkReport")
        if not _SHA256_RE.fullmatch(self.manifest_sha256):
            raise ValueError("manifest_sha256 must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class ExtractionSelectivityEvidence:
    """Manifest-bound observations for one benchmark split and its selectivity curve."""

    split: BenchmarkSplit
    manifest_sha256: str
    observations: tuple[ExtractionThresholdObservation, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.split, BenchmarkSplit):
            raise TypeError("selectivity evidence split must be a BenchmarkSplit")
        if not _SHA256_RE.fullmatch(self.manifest_sha256):
            raise ValueError("selectivity evidence manifest_sha256 must be a lowercase SHA-256 digest")
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise ValueError("selectivity evidence schema_version must be 1")
        if not self.observations:
            raise ValueError("selectivity evidence requires at least one threshold observation")
        wrong_split = [
            observation.threshold_id
            for observation in self.observations
            if observation.split is not self.split
        ]
        if wrong_split:
            raise ValueError(
                "selectivity evidence observations must all use the declared split: "
                f"{tuple(sorted(wrong_split))!r}"
            )
        wrong_manifest = [
            observation.threshold_id
            for observation in self.observations
            if observation.manifest_sha256 != self.manifest_sha256
        ]
        if wrong_manifest:
            raise ValueError(
                "selectivity evidence observations must all use the declared manifest: "
                f"{tuple(sorted(wrong_manifest))!r}"
            )
        ids = [observation.threshold_id for observation in self.observations]
        if len(set(ids)) != len(ids):
            raise ValueError("selectivity evidence threshold_id values must be unique")
        thresholds = [float(observation.threshold) for observation in self.observations]
        if len(set(thresholds)) != len(thresholds):
            raise ValueError("selectivity evidence threshold values must be unique")

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
            "report": _report_payload(observation.report),
        }
        for observation in sorted(observations, key=lambda item: item.threshold_id)
    ]
    return _stable_sha256(payload)


def select_development_threshold(
    observations: tuple[ExtractionThresholdObservation, ...] | list[ExtractionThresholdObservation],
    *,
    policy: ExtractionThresholdPolicy,
    development_manifest_sha256: str,
) -> FrozenExtractionThreshold:
    observations = tuple(observations)
    if not observations:
        raise ValueError("at least one threshold observation is required")
    if not _SHA256_RE.fullmatch(development_manifest_sha256):
        raise ValueError("development_manifest_sha256 must be a lowercase SHA-256 digest")
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
        if observation.manifest_sha256 != development_manifest_sha256
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
        development_manifest_sha256=development_manifest_sha256,
        development_observation_set_sha256=threshold_observations_sha256(observations),
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

    return ExtractionTestEvaluationLock(
        frozen_threshold_sha256=frozen_threshold.sha256(),
        test_manifest_sha256=test_manifest_sha256,
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
    ).encode("utf-8")
    return sha256(raw).hexdigest()
