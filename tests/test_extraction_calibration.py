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
    ExtractionThresholdObservation,
    ExtractionThresholdPolicy,
    lock_test_evaluation,
    select_development_threshold,
)
from veritas.ingestion import EvidenceKind
from veritas.models import SourceLocation

_MANIFEST_SHA = "a" * 64
_TEST_SHA = "b" * 64


def _source() -> SourceLocation:
    return SourceLocation(artifact_id="paper", page=2, table="Table 1", row="Treatment", column="Estimate")


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
    try:
        select_development_threshold(
            [observation],
            policy=policy,
            development_manifest_sha256=_MANIFEST_SHA,
        )
    except ValueError as exc:
        assert "DEVELOPMENT observations only" in str(exc)
    else:
        raise AssertionError("TEST observations must never participate in threshold selection")


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
