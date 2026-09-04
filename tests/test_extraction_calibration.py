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
    ExtractionSelectivityEvidence,
    ExtractionThresholdObservation,
    ExtractionThresholdPolicy,
    lock_test_evaluation,
    select_development_threshold,
    threshold_observations_sha256,
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


def _observation(
    threshold_id: str,
    threshold: float,
    *,
    accepted: int,
    split: BenchmarkSplit = BenchmarkSplit.DEVELOPMENT,
    manifest_sha256: str = _MANIFEST_SHA,
) -> ExtractionThresholdObservation:
    return ExtractionThresholdObservation(
        threshold_id=threshold_id,
        threshold=threshold,
        split=split,
        report=_report(accepted=accepted),
        manifest_sha256=manifest_sha256,
    )


def test_threshold_selection_rejects_test_observations():
    observation = _observation(
        "t-01",
        0.01,
        accepted=4,
        split=BenchmarkSplit.TEST,
        manifest_sha256=_TEST_SHA,
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


def test_threshold_selection_rejects_manifest_mismatch():
    observation = _observation(
        "t-01",
        0.01,
        accepted=4,
        manifest_sha256=_TEST_SHA,
    )
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.0,
        min_accepted_full_accuracy=0.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    with pytest.raises(ValueError, match="different DEVELOPMENT manifest"):
        select_development_threshold(
            [observation],
            policy=policy,
            development_manifest_sha256=_MANIFEST_SHA,
        )


def test_threshold_selection_prefers_more_coverage_when_risk_policy_is_met():
    observations = [
        _observation("strict", 0.01, accepted=2),
        _observation("broader", 0.02, accepted=4),
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
    assert frozen.development_observation_set_sha256 == threshold_observations_sha256(observations)


def test_frozen_threshold_hash_changes_when_development_reports_change():
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.0,
        min_accepted_full_accuracy=0.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    first_observations = [_observation("t-01", 0.01, accepted=2)]
    second_observations = [_observation("t-01", 0.01, accepted=4)]

    first = select_development_threshold(
        first_observations,
        policy=policy,
        development_manifest_sha256=_MANIFEST_SHA,
    )
    second = select_development_threshold(
        second_observations,
        policy=policy,
        development_manifest_sha256=_MANIFEST_SHA,
    )

    assert first.development_observation_set_sha256 != second.development_observation_set_sha256
    assert first.sha256() != second.sha256()


def test_selectivity_evidence_rejects_mixed_manifest_observations():
    observations = (
        _observation("t-01", 0.01, accepted=2),
        _observation("t-02", 0.02, accepted=4, manifest_sha256=_TEST_SHA),
    )
    with pytest.raises(ValueError, match="declared manifest"):
        ExtractionSelectivityEvidence(
            split=BenchmarkSplit.DEVELOPMENT,
            manifest_sha256=_MANIFEST_SHA,
            observations=observations,
        )


def test_test_evaluation_lock_binds_frozen_threshold_without_retuning_api():
    observation = _observation("dev-selected", 0.02, accepted=4)
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
