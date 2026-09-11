from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .extraction_benchmark import (
    ExtractionBenchmarkReport,
    ExtractionSelectivityCurve,
    ExtractionSelectivityPoint,
)
from .extraction_calibration import (
    ExtractionTestEvaluationLock,
    ExtractionThresholdPolicy,
    FrozenExtractionThreshold,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_POLICY_ROOT_KEYS = frozenset(
    {
        "as_of",
        "benchmark_confidence",
        "bound_evidence_plan_sha256",
        "current_design_power",
        "interpretation",
        "production_authorized",
        "production_boundary",
        "schema_version",
        "status",
        "threshold_policy",
        "threshold_policy_sha256",
    }
)
_POLICY_KEYS = frozenset(
    {
        "schema_version",
        "min_selective_coverage",
        "min_accepted_full_accuracy",
        "max_critical_family_wrong_accept_upper_bound",
    }
)
_FREEZE_KEYS = frozenset(
    {
        "schema_version",
        "evidence_plan_sha256",
        "development_manifest_sha256",
        "benchmark_confidence",
        "pilot_policy_file_sha256",
        "threshold_policy",
        "threshold_policy_sha256",
        "observations",
        "selectivity_curve",
        "frozen_threshold",
        "frozen_threshold_sha256",
        "production_authorized",
    }
)
_OBSERVATION_KEYS = frozenset(
    {
        "threshold_id",
        "threshold",
        "prediction_artifact_sha256",
        "prediction_semantics_sha256",
        "benchmark_report_sha256",
        "targets",
        "accepted",
        "fully_correct_accepts",
        "wrong_accepts",
        "abstentions",
        "conflicts",
        "domain_shifts",
        "selective_coverage",
        "accepted_full_accuracy",
        "wrong_accept_rate",
        "accepted_value_accuracy",
        "accepted_source_accuracy",
        "field_targets",
        "accepted_field_targets",
        "accepted_field_value_accuracy",
        "table_row_targets",
        "accepted_table_row_targets",
        "accepted_table_row_identity_accuracy",
        "semantic_gate_targets",
        "accepted_semantic_gate_targets",
        "accepted_semantic_gate_accuracy",
        "critical_article_families",
        "critical_wrong_accept_families",
        "critical_family_wrong_accept_rate",
        "critical_family_wrong_accept_upper_bound",
    }
)
_SELECTIVITY_POINT_KEYS = frozenset(
    {
        "threshold",
        "selective_coverage",
        "accepted_full_accuracy",
        "accepted_field_value_accuracy",
        "accepted_table_row_identity_accuracy",
        "accepted_semantic_gate_accuracy",
        "wrong_accept_rate",
        "critical_family_wrong_accept_upper_bound",
    }
)
_FROZEN_THRESHOLD_KEYS = frozenset(
    {
        "schema_version",
        "threshold_id",
        "threshold",
        "development_manifest_sha256",
        "policy_sha256",
        "candidate_threshold_ids",
    }
)
_TEST_ARCHIVE_KEYS = frozenset(
    {
        "schema_version",
        "development_calibration_freeze_sha256",
        "development_calibration_freeze_file_sha256",
        "frozen_threshold_sha256",
        "test_manifest_sha256",
        "test_manifest_file_sha256",
        "test_evaluation_lock",
        "test_evaluation_lock_sha256",
        "production_authorized",
    }
)
_TEST_LOCK_KEYS = frozenset(
    {
        "schema_version",
        "frozen_threshold_sha256",
        "test_manifest_sha256",
    }
)


@dataclass(frozen=True)
class ExtractionPretestPilotThresholdPolicy:
    bound_evidence_plan_sha256: str
    benchmark_confidence: float
    threshold_policy: ExtractionThresholdPolicy
    source_file_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(
            self.bound_evidence_plan_sha256,
            label="bound_evidence_plan_sha256",
        )
        _require_probability(self.benchmark_confidence, label="benchmark_confidence")
        if not isinstance(self.threshold_policy, ExtractionThresholdPolicy):
            raise TypeError("threshold_policy must be an ExtractionThresholdPolicy")
        _require_sha256(self.source_file_sha256, label="source_file_sha256")


@dataclass(frozen=True)
class ExtractionDevelopmentCalibrationObservationArchive:
    threshold_id: str
    threshold: float
    prediction_artifact_sha256: str
    prediction_semantics_sha256: str
    benchmark_report_sha256: str
    targets: int
    accepted: int
    fully_correct_accepts: int
    wrong_accepts: int
    abstentions: int
    conflicts: int
    domain_shifts: int
    selective_coverage: float
    accepted_full_accuracy: float
    wrong_accept_rate: float
    accepted_value_accuracy: float
    accepted_source_accuracy: float
    field_targets: int
    accepted_field_targets: int
    accepted_field_value_accuracy: float
    table_row_targets: int
    accepted_table_row_targets: int
    accepted_table_row_identity_accuracy: float
    semantic_gate_targets: int
    accepted_semantic_gate_targets: int
    accepted_semantic_gate_accuracy: float
    critical_article_families: int
    critical_wrong_accept_families: int
    critical_family_wrong_accept_rate: float
    critical_family_wrong_accept_upper_bound: float

    def __post_init__(self) -> None:
        _require_nonempty_string(self.threshold_id, label="threshold_id")
        _require_finite_nonnegative_number(self.threshold, label="threshold")
        for label, value in (
            ("prediction_artifact_sha256", self.prediction_artifact_sha256),
            ("prediction_semantics_sha256", self.prediction_semantics_sha256),
            ("benchmark_report_sha256", self.benchmark_report_sha256),
        ):
            _require_sha256(value, label=label)
        for label, value in (
            ("targets", self.targets),
            ("accepted", self.accepted),
            ("fully_correct_accepts", self.fully_correct_accepts),
            ("wrong_accepts", self.wrong_accepts),
            ("abstentions", self.abstentions),
            ("conflicts", self.conflicts),
            ("domain_shifts", self.domain_shifts),
            ("field_targets", self.field_targets),
            ("accepted_field_targets", self.accepted_field_targets),
            ("table_row_targets", self.table_row_targets),
            ("accepted_table_row_targets", self.accepted_table_row_targets),
            ("semantic_gate_targets", self.semantic_gate_targets),
            ("accepted_semantic_gate_targets", self.accepted_semantic_gate_targets),
            ("critical_article_families", self.critical_article_families),
            ("critical_wrong_accept_families", self.critical_wrong_accept_families),
        ):
            _require_nonnegative_int(value, label=label)
        for label, value in (
            ("selective_coverage", self.selective_coverage),
            ("accepted_full_accuracy", self.accepted_full_accuracy),
            ("wrong_accept_rate", self.wrong_accept_rate),
            ("accepted_value_accuracy", self.accepted_value_accuracy),
            ("accepted_source_accuracy", self.accepted_source_accuracy),
            ("accepted_field_value_accuracy", self.accepted_field_value_accuracy),
            (
                "accepted_table_row_identity_accuracy",
                self.accepted_table_row_identity_accuracy,
            ),
            ("accepted_semantic_gate_accuracy", self.accepted_semantic_gate_accuracy),
            (
                "critical_family_wrong_accept_rate",
                self.critical_family_wrong_accept_rate,
            ),
            (
                "critical_family_wrong_accept_upper_bound",
                self.critical_family_wrong_accept_upper_bound,
            ),
        ):
            _require_probability(value, label=label)

    @classmethod
    def from_report(
        cls,
        *,
        threshold_id: str,
        threshold: float,
        prediction_artifact_sha256: str,
        prediction_semantics_sha256: str,
        report: ExtractionBenchmarkReport,
    ) -> ExtractionDevelopmentCalibrationObservationArchive:
        if not isinstance(report, ExtractionBenchmarkReport):
            raise TypeError("report must be an ExtractionBenchmarkReport")
        return cls(
            threshold_id=threshold_id,
            threshold=threshold,
            prediction_artifact_sha256=prediction_artifact_sha256,
            prediction_semantics_sha256=prediction_semantics_sha256,
            benchmark_report_sha256=extraction_benchmark_report_sha256(report),
            targets=report.targets,
            accepted=report.accepted,
            fully_correct_accepts=report.fully_correct_accepts,
            wrong_accepts=report.wrong_accepts,
            abstentions=report.abstentions,
            conflicts=report.conflicts,
            domain_shifts=report.domain_shifts,
            selective_coverage=report.selective_coverage,
            accepted_full_accuracy=report.accepted_full_accuracy,
            wrong_accept_rate=report.wrong_accept_rate,
            accepted_value_accuracy=report.accepted_value_accuracy,
            accepted_source_accuracy=report.accepted_source_accuracy,
            field_targets=report.field_targets,
            accepted_field_targets=report.accepted_field_targets,
            accepted_field_value_accuracy=report.accepted_field_value_accuracy,
            table_row_targets=report.table_row_targets,
            accepted_table_row_targets=report.accepted_table_row_targets,
            accepted_table_row_identity_accuracy=report.accepted_table_row_identity_accuracy,
            semantic_gate_targets=report.semantic_gate_targets,
            accepted_semantic_gate_targets=report.accepted_semantic_gate_targets,
            accepted_semantic_gate_accuracy=report.accepted_semantic_gate_accuracy,
            critical_article_families=report.critical_article_families,
            critical_wrong_accept_families=report.critical_wrong_accept_families,
            critical_family_wrong_accept_rate=report.critical_family_wrong_accept_rate,
            critical_family_wrong_accept_upper_bound=(
                report.critical_family_wrong_accept_upper_bound
            ),
        )

    def selectivity_point(self) -> ExtractionSelectivityPoint:
        return ExtractionSelectivityPoint(
            threshold=self.threshold,
            selective_coverage=self.selective_coverage,
            accepted_full_accuracy=self.accepted_full_accuracy,
            accepted_field_value_accuracy=self.accepted_field_value_accuracy,
            accepted_table_row_identity_accuracy=self.accepted_table_row_identity_accuracy,
            accepted_semantic_gate_accuracy=self.accepted_semantic_gate_accuracy,
            wrong_accept_rate=self.wrong_accept_rate,
            critical_family_wrong_accept_upper_bound=(
                self.critical_family_wrong_accept_upper_bound
            ),
        )


@dataclass(frozen=True)
class ExtractionDevelopmentCalibrationFreeze:
    evidence_plan_sha256: str
    development_manifest_sha256: str
    benchmark_confidence: float
    pilot_policy_file_sha256: str
    threshold_policy: ExtractionThresholdPolicy
    observations: tuple[ExtractionDevelopmentCalibrationObservationArchive, ...]
    selectivity_curve: ExtractionSelectivityCurve
    frozen_threshold: FrozenExtractionThreshold
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_plan_sha256, label="evidence_plan_sha256")
        _require_sha256(
            self.development_manifest_sha256,
            label="development_manifest_sha256",
        )
        _require_probability(self.benchmark_confidence, label="benchmark_confidence")
        _require_sha256(self.pilot_policy_file_sha256, label="pilot_policy_file_sha256")
        if not isinstance(self.threshold_policy, ExtractionThresholdPolicy):
            raise TypeError("threshold_policy must be an ExtractionThresholdPolicy")
        if not isinstance(self.observations, tuple) or not self.observations:
            raise ValueError("development calibration freeze requires observations")
        if any(
            not isinstance(item, ExtractionDevelopmentCalibrationObservationArchive)
            for item in self.observations
        ):
            raise TypeError("development calibration observations are invalid")
        ids = [item.threshold_id for item in self.observations]
        if len(set(ids)) != len(ids):
            raise ValueError("development calibration threshold ids must be unique")
        if not isinstance(self.selectivity_curve, ExtractionSelectivityCurve):
            raise TypeError("selectivity_curve must be an ExtractionSelectivityCurve")
        expected_curve = ExtractionSelectivityCurve(
            points=tuple(
                item.selectivity_point()
                for item in sorted(self.observations, key=lambda item: item.threshold)
            )
        )
        if self.selectivity_curve != expected_curve:
            raise ValueError(
                "development calibration selectivity curve differs from archived observations"
            )
        if not isinstance(self.frozen_threshold, FrozenExtractionThreshold):
            raise TypeError("frozen_threshold must be a FrozenExtractionThreshold")
        if self.frozen_threshold.development_manifest_sha256 != self.development_manifest_sha256:
            raise ValueError("frozen threshold uses a different DEVELOPMENT manifest")
        if self.frozen_threshold.policy_sha256 != self.threshold_policy.sha256():
            raise ValueError("frozen threshold uses a different threshold policy")
        if set(self.frozen_threshold.candidate_threshold_ids) != set(ids):
            raise ValueError("frozen threshold candidate ids differ from archived observations")
        selected = {item.threshold_id: item for item in self.observations}.get(
            self.frozen_threshold.threshold_id
        )
        if selected is None or float(selected.threshold) != float(self.frozen_threshold.threshold):
            raise ValueError("frozen threshold selection differs from archived observations")
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("development calibration freezes are non-production only")
        _require_schema_version(self.schema_version, label="development calibration freeze")

    def sha256(self) -> str:
        return _stable_sha256(development_calibration_freeze_json_payload(self))


@dataclass(frozen=True)
class ExtractionTestEvaluationArchive:
    development_calibration_freeze_sha256: str
    development_calibration_freeze_file_sha256: str
    frozen_threshold_sha256: str
    test_manifest_sha256: str
    test_manifest_file_sha256: str
    test_evaluation_lock: ExtractionTestEvaluationLock
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            (
                "development_calibration_freeze_sha256",
                self.development_calibration_freeze_sha256,
            ),
            (
                "development_calibration_freeze_file_sha256",
                self.development_calibration_freeze_file_sha256,
            ),
            ("frozen_threshold_sha256", self.frozen_threshold_sha256),
            ("test_manifest_sha256", self.test_manifest_sha256),
            ("test_manifest_file_sha256", self.test_manifest_file_sha256),
        ):
            _require_sha256(value, label=label)
        if not isinstance(self.test_evaluation_lock, ExtractionTestEvaluationLock):
            raise TypeError("test_evaluation_lock must be an ExtractionTestEvaluationLock")
        if self.test_evaluation_lock.frozen_threshold_sha256 != self.frozen_threshold_sha256:
            raise ValueError("TEST evaluation lock uses a different frozen threshold")
        if self.test_evaluation_lock.test_manifest_sha256 != self.test_manifest_sha256:
            raise ValueError("TEST evaluation lock uses a different TEST manifest")
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("TEST evaluation archives are non-production only")
        _require_schema_version(self.schema_version, label="TEST evaluation archive")

    def sha256(self) -> str:
        return _stable_sha256(test_evaluation_archive_json_payload(self))


def load_pretest_pilot_threshold_policy(
    path: str | Path,
) -> ExtractionPretestPilotThresholdPolicy:
    source_path = Path(path)
    raw = source_path.read_bytes()
    payload = _loads_strict_json_bytes(raw, label="pre-TEST pilot threshold policy")
    _require_exact_keys(payload, _POLICY_ROOT_KEYS, label="pre-TEST pilot threshold policy")
    _require_schema_version(
        payload["schema_version"],
        label="pre-TEST pilot threshold policy",
    )
    if payload["status"] != "frozen_nonproduction_pilot_threshold_policy":
        raise ValueError("pre-TEST pilot threshold policy has an unsupported status")
    if payload["production_authorized"] is not False:
        raise ValueError("pre-TEST pilot threshold policy must remain non-production")
    _require_nonempty_string(payload["as_of"], label="pre-TEST pilot threshold policy as_of")
    _require_nonempty_string(
        payload["interpretation"],
        label="pre-TEST pilot threshold policy interpretation",
    )
    _require_nonempty_string(
        payload["production_boundary"],
        label="pre-TEST pilot threshold policy production_boundary",
    )
    if not isinstance(payload["current_design_power"], dict):
        raise TypeError("pre-TEST pilot threshold policy current_design_power must be an object")
    policy_payload = payload["threshold_policy"]
    _require_exact_keys(policy_payload, _POLICY_KEYS, label="threshold policy")
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=policy_payload["min_selective_coverage"],
        min_accepted_full_accuracy=policy_payload["min_accepted_full_accuracy"],
        max_critical_family_wrong_accept_upper_bound=policy_payload[
            "max_critical_family_wrong_accept_upper_bound"
        ],
        schema_version=policy_payload["schema_version"],
    )
    archived_policy_sha256 = payload["threshold_policy_sha256"]
    _require_sha256(archived_policy_sha256, label="threshold_policy_sha256")
    if policy.sha256() != archived_policy_sha256:
        raise ValueError("pre-TEST pilot threshold policy SHA-256 does not match policy payload")
    return ExtractionPretestPilotThresholdPolicy(
        bound_evidence_plan_sha256=payload["bound_evidence_plan_sha256"],
        benchmark_confidence=payload["benchmark_confidence"],
        threshold_policy=policy,
        source_file_sha256=sha256(raw).hexdigest(),
    )


def development_calibration_freeze_json_payload(
    freeze: ExtractionDevelopmentCalibrationFreeze,
) -> dict[str, object]:
    if not isinstance(freeze, ExtractionDevelopmentCalibrationFreeze):
        raise TypeError("freeze must be an ExtractionDevelopmentCalibrationFreeze")
    return {
        "schema_version": freeze.schema_version,
        "evidence_plan_sha256": freeze.evidence_plan_sha256,
        "development_manifest_sha256": freeze.development_manifest_sha256,
        "benchmark_confidence": freeze.benchmark_confidence,
        "pilot_policy_file_sha256": freeze.pilot_policy_file_sha256,
        "threshold_policy": _threshold_policy_payload(freeze.threshold_policy),
        "threshold_policy_sha256": freeze.threshold_policy.sha256(),
        "observations": [
            _observation_payload(item)
            for item in sorted(freeze.observations, key=lambda item: item.threshold_id)
        ],
        "selectivity_curve": [
            _selectivity_point_payload(point) for point in freeze.selectivity_curve.points
        ],
        "frozen_threshold": _frozen_threshold_payload(freeze.frozen_threshold),
        "frozen_threshold_sha256": freeze.frozen_threshold.sha256(),
        "production_authorized": freeze.production_authorized,
    }


def load_development_calibration_freeze(
    path: str | Path,
) -> ExtractionDevelopmentCalibrationFreeze:
    payload = _load_strict_json_file(path, label="development calibration freeze")
    _require_exact_keys(payload, _FREEZE_KEYS, label="development calibration freeze")
    policy_payload = payload["threshold_policy"]
    _require_exact_keys(policy_payload, _POLICY_KEYS, label="threshold policy")
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=policy_payload["min_selective_coverage"],
        min_accepted_full_accuracy=policy_payload["min_accepted_full_accuracy"],
        max_critical_family_wrong_accept_upper_bound=policy_payload[
            "max_critical_family_wrong_accept_upper_bound"
        ],
        schema_version=policy_payload["schema_version"],
    )
    _require_sha256(payload["threshold_policy_sha256"], label="threshold_policy_sha256")
    if policy.sha256() != payload["threshold_policy_sha256"]:
        raise ValueError("development calibration threshold policy SHA-256 differs")

    observation_rows = payload["observations"]
    if not isinstance(observation_rows, list) or not observation_rows:
        raise ValueError("development calibration observations must be a non-empty array")
    observations = tuple(
        _observation_from_mapping(row, index=index)
        for index, row in enumerate(observation_rows)
    )

    curve_rows = payload["selectivity_curve"]
    if not isinstance(curve_rows, list) or not curve_rows:
        raise ValueError("development calibration selectivity_curve must be a non-empty array")
    curve = ExtractionSelectivityCurve(
        points=tuple(
            _selectivity_point_from_mapping(row, index=index)
            for index, row in enumerate(curve_rows)
        )
    )

    frozen_payload = payload["frozen_threshold"]
    _require_exact_keys(frozen_payload, _FROZEN_THRESHOLD_KEYS, label="frozen threshold")
    candidate_ids = frozen_payload["candidate_threshold_ids"]
    if not isinstance(candidate_ids, list):
        raise TypeError("frozen threshold candidate_threshold_ids must be an array")
    frozen = FrozenExtractionThreshold(
        threshold_id=frozen_payload["threshold_id"],
        threshold=frozen_payload["threshold"],
        development_manifest_sha256=frozen_payload["development_manifest_sha256"],
        policy_sha256=frozen_payload["policy_sha256"],
        candidate_threshold_ids=tuple(candidate_ids),
        schema_version=frozen_payload["schema_version"],
    )
    _require_sha256(payload["frozen_threshold_sha256"], label="frozen_threshold_sha256")
    if frozen.sha256() != payload["frozen_threshold_sha256"]:
        raise ValueError("development calibration frozen-threshold SHA-256 differs")

    return ExtractionDevelopmentCalibrationFreeze(
        evidence_plan_sha256=payload["evidence_plan_sha256"],
        development_manifest_sha256=payload["development_manifest_sha256"],
        benchmark_confidence=payload["benchmark_confidence"],
        pilot_policy_file_sha256=payload["pilot_policy_file_sha256"],
        threshold_policy=policy,
        observations=observations,
        selectivity_curve=curve,
        frozen_threshold=frozen,
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def test_evaluation_archive_json_payload(
    archive: ExtractionTestEvaluationArchive,
) -> dict[str, object]:
    if not isinstance(archive, ExtractionTestEvaluationArchive):
        raise TypeError("archive must be an ExtractionTestEvaluationArchive")
    return {
        "schema_version": archive.schema_version,
        "development_calibration_freeze_sha256": (
            archive.development_calibration_freeze_sha256
        ),
        "development_calibration_freeze_file_sha256": (
            archive.development_calibration_freeze_file_sha256
        ),
        "frozen_threshold_sha256": archive.frozen_threshold_sha256,
        "test_manifest_sha256": archive.test_manifest_sha256,
        "test_manifest_file_sha256": archive.test_manifest_file_sha256,
        "test_evaluation_lock": {
            "schema_version": archive.test_evaluation_lock.schema_version,
            "frozen_threshold_sha256": archive.test_evaluation_lock.frozen_threshold_sha256,
            "test_manifest_sha256": archive.test_evaluation_lock.test_manifest_sha256,
        },
        "test_evaluation_lock_sha256": archive.test_evaluation_lock.sha256(),
        "production_authorized": archive.production_authorized,
    }


def load_test_evaluation_archive(path: str | Path) -> ExtractionTestEvaluationArchive:
    payload = _load_strict_json_file(path, label="TEST evaluation archive")
    _require_exact_keys(payload, _TEST_ARCHIVE_KEYS, label="TEST evaluation archive")
    lock_payload = payload["test_evaluation_lock"]
    _require_exact_keys(lock_payload, _TEST_LOCK_KEYS, label="TEST evaluation lock")
    lock = ExtractionTestEvaluationLock(
        frozen_threshold_sha256=lock_payload["frozen_threshold_sha256"],
        test_manifest_sha256=lock_payload["test_manifest_sha256"],
        schema_version=lock_payload["schema_version"],
    )
    _require_sha256(
        payload["test_evaluation_lock_sha256"], label="test_evaluation_lock_sha256"
    )
    if lock.sha256() != payload["test_evaluation_lock_sha256"]:
        raise ValueError("TEST evaluation lock SHA-256 differs")
    return ExtractionTestEvaluationArchive(
        development_calibration_freeze_sha256=payload[
            "development_calibration_freeze_sha256"
        ],
        development_calibration_freeze_file_sha256=payload[
            "development_calibration_freeze_file_sha256"
        ],
        frozen_threshold_sha256=payload["frozen_threshold_sha256"],
        test_manifest_sha256=payload["test_manifest_sha256"],
        test_manifest_file_sha256=payload["test_manifest_file_sha256"],
        test_evaluation_lock=lock,
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def extraction_benchmark_report_sha256(report: ExtractionBenchmarkReport) -> str:
    if not isinstance(report, ExtractionBenchmarkReport):
        raise TypeError("report must be an ExtractionBenchmarkReport")
    return _stable_sha256(
        {
            "targets": report.targets,
            "accepted": report.accepted,
            "fully_correct_accepts": report.fully_correct_accepts,
            "wrong_accepts": report.wrong_accepts,
            "abstentions": report.abstentions,
            "conflicts": report.conflicts,
            "domain_shifts": report.domain_shifts,
            "selective_coverage": report.selective_coverage,
            "accepted_full_accuracy": report.accepted_full_accuracy,
            "wrong_accept_rate": report.wrong_accept_rate,
            "accepted_value_accuracy": report.accepted_value_accuracy,
            "accepted_source_accuracy": report.accepted_source_accuracy,
            "field_targets": report.field_targets,
            "accepted_field_targets": report.accepted_field_targets,
            "accepted_field_value_accuracy": report.accepted_field_value_accuracy,
            "table_row_targets": report.table_row_targets,
            "accepted_table_row_targets": report.accepted_table_row_targets,
            "accepted_table_row_identity_accuracy": (
                report.accepted_table_row_identity_accuracy
            ),
            "semantic_gate_targets": report.semantic_gate_targets,
            "accepted_semantic_gate_targets": report.accepted_semantic_gate_targets,
            "accepted_semantic_gate_accuracy": report.accepted_semantic_gate_accuracy,
            "critical_article_families": report.critical_article_families,
            "critical_wrong_accept_families": report.critical_wrong_accept_families,
            "critical_family_wrong_accept_rate": report.critical_family_wrong_accept_rate,
            "critical_family_wrong_accept_upper_bound": (
                report.critical_family_wrong_accept_upper_bound
            ),
            "outcomes": [
                {
                    "target_id": outcome.target_id,
                    "paper_id": outcome.paper_id,
                    "article_family_id": outcome.article_family_id,
                    "kind": outcome.kind.value,
                    "critical_for_hard_audit": outcome.critical_for_hard_audit,
                    "decision": outcome.decision.value,
                    "accepted": outcome.accepted,
                    "value_correct": outcome.value_correct,
                    "source_correct": outcome.source_correct,
                    "page_correct": outcome.page_correct,
                    "display_item_correct": outcome.display_item_correct,
                    "row_correct": outcome.row_correct,
                    "column_correct": outcome.column_correct,
                }
                for outcome in report.outcomes
            ],
        }
    )


def _threshold_policy_payload(policy: ExtractionThresholdPolicy) -> dict[str, object]:
    return {
        "schema_version": policy.schema_version,
        "min_selective_coverage": policy.min_selective_coverage,
        "min_accepted_full_accuracy": policy.min_accepted_full_accuracy,
        "max_critical_family_wrong_accept_upper_bound": (
            policy.max_critical_family_wrong_accept_upper_bound
        ),
    }


def _observation_payload(
    observation: ExtractionDevelopmentCalibrationObservationArchive,
) -> dict[str, object]:
    return {key: getattr(observation, key) for key in sorted(_OBSERVATION_KEYS)}


def _observation_from_mapping(
    value: object,
    *,
    index: int,
) -> ExtractionDevelopmentCalibrationObservationArchive:
    label = f"development calibration observation {index}"
    _require_exact_keys(value, _OBSERVATION_KEYS, label=label)
    return ExtractionDevelopmentCalibrationObservationArchive(
        **{key: value[key] for key in _OBSERVATION_KEYS}
    )


def _selectivity_point_payload(point: ExtractionSelectivityPoint) -> dict[str, object]:
    return {
        "threshold": point.threshold,
        "selective_coverage": point.selective_coverage,
        "accepted_full_accuracy": point.accepted_full_accuracy,
        "accepted_field_value_accuracy": point.accepted_field_value_accuracy,
        "accepted_table_row_identity_accuracy": point.accepted_table_row_identity_accuracy,
        "accepted_semantic_gate_accuracy": point.accepted_semantic_gate_accuracy,
        "wrong_accept_rate": point.wrong_accept_rate,
        "critical_family_wrong_accept_upper_bound": (
            point.critical_family_wrong_accept_upper_bound
        ),
    }


def _selectivity_point_from_mapping(
    value: object,
    *,
    index: int,
) -> ExtractionSelectivityPoint:
    label = f"development calibration selectivity point {index}"
    _require_exact_keys(value, _SELECTIVITY_POINT_KEYS, label=label)
    return ExtractionSelectivityPoint(
        threshold=value["threshold"],
        selective_coverage=value["selective_coverage"],
        accepted_full_accuracy=value["accepted_full_accuracy"],
        accepted_field_value_accuracy=value["accepted_field_value_accuracy"],
        accepted_table_row_identity_accuracy=value[
            "accepted_table_row_identity_accuracy"
        ],
        accepted_semantic_gate_accuracy=value["accepted_semantic_gate_accuracy"],
        wrong_accept_rate=value["wrong_accept_rate"],
        critical_family_wrong_accept_upper_bound=value[
            "critical_family_wrong_accept_upper_bound"
        ],
    )


def _frozen_threshold_payload(frozen: FrozenExtractionThreshold) -> dict[str, object]:
    return {
        "schema_version": frozen.schema_version,
        "threshold_id": frozen.threshold_id,
        "threshold": frozen.threshold,
        "development_manifest_sha256": frozen.development_manifest_sha256,
        "policy_sha256": frozen.policy_sha256,
        "candidate_threshold_ids": list(frozen.candidate_threshold_ids),
    }


def _load_strict_json_file(path: str | Path, *, label: str) -> dict[str, Any]:
    payload = _loads_strict_json_bytes(Path(path).read_bytes(), label=label)
    if not isinstance(payload, dict):
        raise TypeError(f"{label} root must be an object")
    return payload


def _loads_strict_json_bytes(raw: bytes, *, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc

    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"{label} contains non-standard JSON number: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc


def _require_exact_keys(value: object, expected: frozenset[str], *, label: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        unknown = tuple(sorted(actual - expected))
        raise ValueError(
            f"{label} keys differ from schema; missing={missing!r}, unknown={unknown!r}"
        )


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_nonnegative_int(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


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
