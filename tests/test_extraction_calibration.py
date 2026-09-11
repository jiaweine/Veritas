from dataclasses import replace

import pytest

from veritas.benchmark import BenchmarkSplit
from veritas.extraction import (
    ConformalCalibration,
    ConformalExtractionGate,
    ExtractionCandidate,
)
from veritas.extraction_benchmark import (
    ExtractionGoldTarget,
    ExtractionPrediction,
    evaluate_extraction_benchmark,
)
from veritas.extraction_calibration import (
    ExtractionTestEvaluationLock,
    ExtractionThresholdObservation,
    ExtractionThresholdPolicy,
    FrozenExtractionThreshold,
    lock_test_evaluation,
    select_development_threshold,
)
from veritas.ingestion import EvidenceKind
from veritas.models import SourceLocation

_MANIFEST_SHA = "a" * 64
_TEST_SHA = "b" * 64


def _source() -> SourceLocation:
    return SourceLocation(
        artifact_id="paper",
        page=2,
        table="Table 1",
        row="Treatment",
        column="Estimate",
    )


def _gold(target_id: str, family: str) -> ExtractionGoldTarget:
    return ExtractionGoldTarget(
        target_id=target_id,
        paper_id=f"paper-{family}",
        article_family_id=family,
        object_type="RegressionResult",
        key="beta",
        kind=EvidenceKind.FIELD,
        accepted_normalized_values=("0.18",),
        source=_source(),
        reviewers=("reviewer-a", "reviewer-b"),
        adjudicated=True,
    )


def _prediction(target_id: str) -> ExtractionPrediction:
    gate = ConformalExtractionGate(ConformalCalibration((0.01, 0.02, 0.03), alpha=0.25))
    resolution = gate.resolve(
        [
            ExtractionCandidate("native", "native_pdf", "0.18", "0.18", 0.01, _source()),
            ExtractionCandidate("vision", "vision_language", "0.18", "0.18", 0.02, _source()),
        ]
    )
    return ExtractionPrediction(target_id=target_id, resolution=resolution)


def _report(*, accepted: int, total: int = 4):
    gold = [_gold(f"t{index}", f"fam-{index}") for index in range(total)]
    predictions = [_prediction(f"t{index}") for index in range(accepted)]
    return evaluate_extraction_benchmark(gold, predictions)


def _frozen() -> FrozenExtractionThreshold:
    return FrozenExtractionThreshold(
        threshold_id="t-01",
        threshold=0.01,
        development_manifest_sha256=_MANIFEST_SHA,
        policy_sha256="c" * 64,
        candidate_threshold_ids=("t-01",),
    )


def test_threshold_selection_rejects_test_observations():
    observation = ExtractionThresholdObservation(
        threshold_id="t-01",
        threshold=0.01,
        split=BenchmarkSplit.TEST,
        report=_report(accepted=4),
    )
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.0,
        min_accepted_full_accuracy=0.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    with pytest.raises(ValueError, match="DEVELOPMENT observations only"):
        select_development_threshold(
            [observation],
            policy=policy,
            development_manifest_sha256=_MANIFEST_SHA,
        )


def test_threshold_selection_prefers_more_coverage_when_risk_policy_is_met():
    observations = [
        ExtractionThresholdObservation(
            threshold_id="strict",
            threshold=0.01,
            split=BenchmarkSplit.DEVELOPMENT,
            report=_report(accepted=2),
        ),
        ExtractionThresholdObservation(
            threshold_id="broader",
            threshold=0.02,
            split=BenchmarkSplit.DEVELOPMENT,
            report=_report(accepted=4),
        ),
    ]
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.25,
        min_accepted_full_accuracy=1.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    frozen = select_development_threshold(
        observations,
        policy=policy,
        development_manifest_sha256=_MANIFEST_SHA,
    )
    assert frozen.threshold_id == "broader"
    assert frozen.threshold == 0.02
    assert frozen.candidate_threshold_ids == ("broader", "strict")


def test_test_evaluation_lock_binds_frozen_threshold_without_retuning_api():
    observation = ExtractionThresholdObservation(
        threshold_id="dev-selected",
        threshold=0.02,
        split=BenchmarkSplit.DEVELOPMENT,
        report=_report(accepted=4),
    )
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.0,
        min_accepted_full_accuracy=1.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    frozen = select_development_threshold(
        [observation],
        policy=policy,
        development_manifest_sha256=_MANIFEST_SHA,
    )
    test_lock = lock_test_evaluation(frozen, test_manifest_sha256=_TEST_SHA)
    assert test_lock.frozen_threshold_sha256 == frozen.sha256()
    assert test_lock.test_manifest_sha256 == _TEST_SHA
    assert test_lock.sha256() != frozen.sha256()


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -float("inf")])
def test_threshold_observation_rejects_boolean_or_nonfinite_threshold(value):
    with pytest.raises(ValueError, match="finite non-negative"):
        ExtractionThresholdObservation(
            threshold_id="bad",
            threshold=value,
            split=BenchmarkSplit.DEVELOPMENT,
            report=_report(accepted=4),
        )


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_threshold_policy_rejects_boolean_or_nonfinite_probability(value):
    with pytest.raises(ValueError, match="finite number"):
        ExtractionThresholdPolicy(min_selective_coverage=value)


def test_frozen_threshold_rejects_invalid_candidates_and_nonfinite_thresholds():
    with pytest.raises(ValueError, match="finite non-negative"):
        replace(_frozen(), threshold=float("nan"))
    with pytest.raises(ValueError, match="unique"):
        replace(_frozen(), candidate_threshold_ids=("t-01", "t-01"))
    with pytest.raises(ValueError, match="present in candidate"):
        replace(_frozen(), threshold_id="not-a-candidate")
    with pytest.raises(ValueError, match="candidate threshold id"):
        replace(_frozen(), candidate_threshold_ids=("",))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ExtractionThresholdPolicy(schema_version=2),
        lambda: replace(_frozen(), schema_version=True),
        lambda: ExtractionTestEvaluationLock(
            frozen_threshold_sha256="c" * 64,
            test_manifest_sha256="d" * 64,
            schema_version=2,
        ),
    ],
)
def test_calibration_commitments_reject_unsupported_schema_versions(factory):
    with pytest.raises(ValueError, match="schema_version must be 1"):
        factory()


def test_calibration_hash_inputs_are_typed_and_fail_closed():
    with pytest.raises(ValueError, match="development_manifest_sha256"):
        select_development_threshold(
            [
                ExtractionThresholdObservation(
                    threshold_id="t-01",
                    threshold=0.01,
                    split=BenchmarkSplit.DEVELOPMENT,
                    report=_report(accepted=4),
                )
            ],
            policy=ExtractionThresholdPolicy(
                min_selective_coverage=0.0,
                min_accepted_full_accuracy=0.0,
                max_critical_family_wrong_accept_upper_bound=1.0,
            ),
            development_manifest_sha256=True,
        )
    with pytest.raises(ValueError, match="test_manifest_sha256"):
        lock_test_evaluation(_frozen(), test_manifest_sha256=True)
