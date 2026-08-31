from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256

from .benchmark import BenchmarkSplit
from .extraction_benchmark import ExtractionBenchmarkReport

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExtractionThresholdObservation:
    threshold_id: str
    threshold: float
    split: BenchmarkSplit
    report: ExtractionBenchmarkReport

    def __post_init__(self) -> None:
        if not self.threshold_id.strip():
            raise ValueError("threshold_id is required")
        if self.threshold < 0:
            raise ValueError("threshold must be non-negative")


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
    policy_sha256: str
    candidate_threshold_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.threshold_id.strip():
            raise ValueError("threshold_id is required")
        if self.threshold < 0:
            raise ValueError("threshold must be non-negative")
        if not _SHA256_RE.fullmatch(self.development_manifest_sha256):
            raise ValueError("development_manifest_sha256 must be a lowercase SHA-256 digest")
        if not _SHA256_RE.fullmatch(self.policy_sha256):
            raise ValueError("policy_sha256 must be a lowercase SHA-256 digest")
        if not self.candidate_threshold_ids:
            raise ValueError("candidate_threshold_ids cannot be empty")

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

    return ExtractionTestEvaluationLock(
        frozen_threshold_sha256=frozen_threshold.sha256(),
        test_manifest_sha256=test_manifest_sha256,
    )
