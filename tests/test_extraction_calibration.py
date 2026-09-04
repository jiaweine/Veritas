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
)
from veritas.extraction_calibration import (
    ExtractionSelectivityEvidence,
    ExtractionThresholdObservation,
    ExtractionThresholdPolicy,
    lock_test_evaluation,
    select_development_threshold,
    threshold_observations_sha256,
)
from veritas.extraction_review import ExtractionGoldManifest
from veritas.extraction_split_manifest import ExtractionSplitManifest
from veritas.ingestion import EvidenceKind
from veritas.models import SourceLocation

_SEED_SHA = "c" * 64


def _source() -> SourceLocation:
    return SourceLocation(
        artifact_id="paper",
        page=2,
        table="Table 1",
        row="Treatment",
        column="Estimate",
    )


def _gold(target_id: str, family: str, index: int) -> ExtractionGoldTarget:
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
        review_record_sha256=f"{index % 16:x}" * 64,
    )


def _gold_manifest(count: int = 32) -> ExtractionGoldManifest:
    return ExtractionGoldManifest(
        targets=tuple(
            _gold(f"t{index:02d}", f"fam-{index:02d}", index) for index in range(count)
        ),
        split_salt="calibration-manifest-v1",
        source_seed_manifest_sha256=_SEED_SHA,
    )


def _split_manifests() -> tuple[ExtractionSplitManifest, ExtractionSplitManifest]:
    gold = _gold_manifest()
    split_lock = gold.build_split_lock()
    return (
        ExtractionSplitManifest(gold, split_lock, BenchmarkSplit.DEVELOPMENT),
        ExtractionSplitManifest(gold, split_lock, BenchmarkSplit.TEST),
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


def _predictions(
    manifest: ExtractionSplitManifest,
    *,
    accepted: int,
) -> tuple[ExtractionPrediction, ...]:
    return tuple(_prediction(target.target_id) for target in manifest.targets[:accepted])


def _observation(
    manifest: ExtractionSplitManifest,
    threshold_id: str,
    threshold: float,
    *,
    accepted: int,
) -> ExtractionThresholdObservation:
    return ExtractionThresholdObservation(
        threshold_id=threshold_id,
        threshold=threshold,
        predictions=_predictions(manifest, accepted=accepted),
        manifest=manifest,
    )


def _permissive_policy() -> ExtractionThresholdPolicy:
    return ExtractionThresholdPolicy(
        min_selective_coverage=0.0,
        min_accepted_full_accuracy=0.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )


def test_threshold_selection_rejects_test_observations():
    development_manifest, test_manifest = _split_manifests()
    observation = _observation(test_manifest, "t-01", 0.01, accepted=len(test_manifest.targets))

    with pytest.raises(ValueError, match="DEVELOPMENT observations only"):
        select_development_threshold(
            [observation],
            policy=_permissive_policy(),
            development_manifest=development_manifest,
        )


def test_threshold_selection_rejects_manifest_mismatch():
    first_development, _ = _split_manifests()
    other_gold = ExtractionGoldManifest(
        targets=first_development.gold_manifest.targets,
        split_salt="different-calibration-v1",
        source_seed_manifest_sha256=_SEED_SHA,
    )
    other_lock = other_gold.build_split_lock()
    other_development = ExtractionSplitManifest(
        other_gold,
        other_lock,
        BenchmarkSplit.DEVELOPMENT,
    )
    observation = _observation(
        other_development,
        "t-01",
        0.01,
        accepted=len(other_development.targets),
    )

    with pytest.raises(ValueError, match="different DEVELOPMENT manifest"):
        select_development_threshold(
            [observation],
            policy=_permissive_policy(),
            development_manifest=first_development,
        )


def test_threshold_selection_prefers_more_coverage_when_risk_policy_is_met():
    development_manifest, _ = _split_manifests()
    total = len(development_manifest.targets)
    observations = [
        _observation(development_manifest, "strict", 0.01, accepted=max(1, total // 2)),
        _observation(development_manifest, "broader", 0.02, accepted=total),
    ]
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.25,
        min_accepted_full_accuracy=1.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    frozen = select_development_threshold(
        observations,
        policy=policy,
        development_manifest=development_manifest,
    )
    assert frozen.threshold_id == "broader"
    assert frozen.threshold == 0.02
    assert frozen.candidate_threshold_ids == ("broader", "strict")
    assert frozen.development_manifest_sha256 == development_manifest.sha256()
    assert frozen.development_observation_set_sha256 == threshold_observations_sha256(observations)


def test_frozen_threshold_hash_changes_when_predictions_change():
    development_manifest, _ = _split_manifests()
    policy = _permissive_policy()
    first_observations = [_observation(development_manifest, "t-01", 0.01, accepted=1)]
    second_observations = [
        _observation(
            development_manifest,
            "t-01",
            0.01,
            accepted=len(development_manifest.targets),
        )
    ]

    first = select_development_threshold(
        first_observations,
        policy=policy,
        development_manifest=development_manifest,
    )
    second = select_development_threshold(
        second_observations,
        policy=policy,
        development_manifest=development_manifest,
    )

    assert first.development_observation_set_sha256 != second.development_observation_set_sha256
    assert first.sha256() != second.sha256()


def test_selectivity_evidence_rejects_mixed_split_manifests():
    development_manifest, test_manifest = _split_manifests()
    observations = (
        _observation(development_manifest, "t-01", 0.01, accepted=1),
        _observation(test_manifest, "t-02", 0.02, accepted=1),
    )
    with pytest.raises(ValueError, match="declared split manifest"):
        ExtractionSelectivityEvidence(
            manifest=development_manifest,
            observations=observations,
        )


def test_observation_rejects_prediction_set_from_wrong_split_membership():
    development_manifest, test_manifest = _split_manifests()
    test_predictions = _predictions(test_manifest, accepted=1)
    with pytest.raises(ValueError, match="unknown gold targets"):
        ExtractionThresholdObservation(
            threshold_id="t-01",
            threshold=0.01,
            predictions=test_predictions,
            manifest=development_manifest,
        )


def test_prediction_set_hash_is_order_independent_but_content_sensitive():
    development_manifest, _ = _split_manifests()
    predictions = _predictions(development_manifest, accepted=min(2, len(development_manifest.targets)))
    first = ExtractionThresholdObservation(
        threshold_id="t-01",
        threshold=0.01,
        predictions=predictions,
        manifest=development_manifest,
    )
    second = ExtractionThresholdObservation(
        threshold_id="t-01",
        threshold=0.01,
        predictions=tuple(reversed(predictions)),
        manifest=development_manifest,
    )
    fewer = ExtractionThresholdObservation(
        threshold_id="t-01",
        threshold=0.01,
        predictions=predictions[:1],
        manifest=development_manifest,
    )

    assert first.prediction_set_sha256() == second.prediction_set_sha256()
    assert first.prediction_set_sha256() != fewer.prediction_set_sha256()


def test_test_evaluation_lock_binds_canonical_test_manifest_without_retuning_api():
    development_manifest, test_manifest = _split_manifests()
    observation = _observation(
        development_manifest,
        "dev-selected",
        0.02,
        accepted=len(development_manifest.targets),
    )
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.0,
        min_accepted_full_accuracy=1.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    frozen = select_development_threshold(
        [observation],
        policy=policy,
        development_manifest=development_manifest,
    )
    test_lock = lock_test_evaluation(frozen, test_manifest=test_manifest)
    assert test_lock.frozen_threshold_sha256 == frozen.sha256()
    assert test_lock.test_manifest_sha256 == test_manifest.sha256()
    assert test_lock.sha256() != frozen.sha256()
