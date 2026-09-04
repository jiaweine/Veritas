from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from veritas.benchmark import BenchmarkSplit
from veritas.corpus import AccessTier, CorpusPaper
from veritas.extraction import ExtractionCandidate, ExtractionDecision, ExtractionResolution
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
)
from veritas.extraction_evidence_workflow import (
    ExtractionEvidencePlan,
    ExtractionSamplingFrame,
    ExtractionSeedManifest,
    ExtractionThresholdGrid,
    build_extraction_evidence_plan,
    build_extraction_evidence_release_receipt,
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)
from veritas.extraction_review import ExtractionGoldManifest
from veritas.extraction_review_packet import ExtractionReviewPacketTarget
from veritas.extraction_split_manifest import ExtractionSplitManifest
from veritas.extraction_test_seal import seal_extraction_test_set
from veritas.ingestion import EvidenceKind
from veritas.models import SourceLocation

_SEED_SHA = "b" * 64


def _paper(index: int) -> CorpusPaper:
    paper_id = f"paper-{index:02d}"
    return CorpusPaper(
        paper_id=paper_id,
        article_family_id=f"family-{index:02d}",
        doi=None,
        title=f"Paper {index}",
        discipline="synthetic_workflow_fixture",
        year=2025,
        source_url=f"https://example.org/{paper_id}",
        access_tier=AccessTier.PAPER_ONLY,
    )


def _sampling_frame(count: int = 64) -> ExtractionSamplingFrame:
    return ExtractionSamplingFrame(
        papers=tuple(_paper(index) for index in range(count)),
        source_manifest_sha256="a" * 64,
    )


def _seed_manifest(frame: ExtractionSamplingFrame) -> ExtractionSeedManifest:
    return ExtractionSeedManifest(
        source_manifest_sha256=_SEED_SHA,
        targets=tuple(
            ExtractionReviewPacketTarget(
                target_id=f"target-{index:02d}",
                case_id=f"case-{index:02d}",
                paper_id=paper.paper_id,
                article_family_id=paper.article_family_id,
                doi=None,
                pdf_url=f"https://example.org/{paper.paper_id}.pdf",
                object_type="RegressionResult",
                key="beta",
                expected_page=2,
                table_label="Table 1",
                row_label=f"row-{index}",
            )
            for index, paper in enumerate(frame.papers)
        ),
    )


def _gold(frame: ExtractionSamplingFrame, *, split_salt: str) -> ExtractionGoldManifest:
    targets = tuple(
        ExtractionGoldTarget(
            target_id=f"target-{index:02d}",
            paper_id=paper.paper_id,
            article_family_id=paper.article_family_id,
            object_type="RegressionResult",
            key="beta",
            kind=EvidenceKind.FIELD,
            accepted_normalized_values=(f"{index / 100:.2f}",),
            source=SourceLocation(
                artifact_id=paper.paper_id,
                page=2,
                table="Table 1",
                row=f"row-{index}",
                column="beta",
            ),
            reviewers=("reviewer-a", "reviewer-b"),
            adjudicated=True,
            review_record_sha256=f"{index % 16:x}" * 64,
        )
        for index, paper in enumerate(frame.papers)
    )
    return ExtractionGoldManifest(
        targets=targets,
        split_salt=split_salt,
        source_seed_manifest_sha256=_SEED_SHA,
    )


def _correct_prediction(target: ExtractionGoldTarget) -> ExtractionPrediction:
    value = target.accepted_normalized_values[0]
    candidates = (
        ExtractionCandidate(
            "native",
            "native_pdf",
            value,
            value,
            0.01,
            target.source,
        ),
        ExtractionCandidate(
            "vision",
            "vision_language",
            value,
            value,
            0.02,
            target.source,
        ),
    )
    return ExtractionPrediction(
        target_id=target.target_id,
        resolution=ExtractionResolution(
            decision=ExtractionDecision.ACCEPT,
            normalized_value=value,
            accepted_candidates=candidates,
            calibration_threshold=0.05,
        ),
    )


def _report(manifest: ExtractionSplitManifest, *, accepted: int):
    predictions = [_correct_prediction(target) for target in manifest.targets[:accepted]]
    return evaluate_extraction_benchmark(manifest.targets, predictions)


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
        report=_report(manifest, accepted=accepted),
        manifest=manifest,
    )


def _threshold_observations(
    manifest: ExtractionSplitManifest,
) -> tuple[ExtractionThresholdObservation, ...]:
    count = len(manifest.targets)
    return (
        _observation(manifest, "t-080", 0.80, accepted=max(1, count // 2)),
        _observation(manifest, "t-090", 0.90, accepted=max(1, (3 * count) // 4)),
        _observation(manifest, "t-095", 0.95, accepted=count),
    )


def _workflow_fixture():
    frame = _sampling_frame()
    seed = _seed_manifest(frame)
    grid = ExtractionThresholdGrid(
        (
            ("t-080", 0.80),
            ("t-090", 0.90),
            ("t-095", 0.95),
        )
    )
    split_salt = "release-workflow-v1"
    gold = _gold(frame, split_salt=split_salt)
    split_lock = gold.build_split_lock()
    development_manifest = ExtractionSplitManifest(
        gold,
        split_lock,
        BenchmarkSplit.DEVELOPMENT,
    )
    test_manifest = ExtractionSplitManifest(
        gold,
        split_lock,
        BenchmarkSplit.TEST,
    )

    plan = build_extraction_evidence_plan(
        frame,
        seed,
        grid,
        split_salt=split_salt,
    )
    development_observations = _threshold_observations(development_manifest)
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.0,
        min_accepted_full_accuracy=1.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    frozen = select_development_threshold(
        development_observations,
        policy=policy,
        development_manifest=development_manifest,
    )
    development_curve_evidence = ExtractionSelectivityEvidence(
        manifest=development_manifest,
        observations=development_observations,
    )
    test_curve_evidence = ExtractionSelectivityEvidence(
        manifest=test_manifest,
        observations=_threshold_observations(test_manifest),
    )
    test_seal = seal_extraction_test_set(gold, split_lock)
    test_lock = lock_test_evaluation(frozen, test_manifest=test_manifest)
    return {
        "frame": frame,
        "seed": seed,
        "grid": grid,
        "plan": plan,
        "gold": gold,
        "split_lock": split_lock,
        "development_manifest": development_manifest,
        "test_seal": test_seal,
        "test_lock": test_lock,
        "test_manifest": test_manifest,
        "frozen": frozen,
        "development_curve_evidence": development_curve_evidence,
        "test_curve_evidence": test_curve_evidence,
    }


def _release(**overrides):
    fixture = _workflow_fixture()
    fixture.update(overrides)
    return build_extraction_evidence_release_receipt(
        plan=fixture["plan"],
        sampling_frame=fixture["frame"],
        seed_manifest=fixture["seed"],
        threshold_grid=fixture["grid"],
        gold_manifest=fixture["gold"],
        split_lock=fixture["split_lock"],
        frozen_threshold=fixture["frozen"],
        development_manifest_sha256=fixture["development_manifest"].sha256(),
        test_seal=fixture["test_seal"],
        test_evaluation_lock=fixture["test_lock"],
        test_manifest_sha256=fixture["test_manifest"].sha256(),
        development_curve_evidence=fixture["development_curve_evidence"],
        test_curve_evidence=fixture["test_curve_evidence"],
    )


def test_repository_sampling_frame_loads_as_unlabeled_exact_bytes_manifest() -> None:
    root = Path(__file__).resolve().parents[1]
    frame = load_extraction_sampling_frame(root / "benchmark/corpus/candidates.json")

    assert frame.status == "sampling_frame_only_unlabeled"
    assert len(frame.papers) >= 8
    assert len(frame.source_manifest_sha256) == 64
    assert len(frame.sha256()) == 64


def test_repository_seed_manifest_loads_exact_bytes_and_review_target_universe() -> None:
    root = Path(__file__).resolve().parents[1]
    seed = load_extraction_seed_manifest(root / "benchmark/extraction/seed_cases_v0.11.json")

    assert seed.status == "seed_corpus_not_locked_gold"
    assert seed.production_hard_finding_authorized is False
    assert len(seed.source_manifest_sha256) == 64
    assert len(seed.sha256()) == 64
    assert len(seed.targets) == 20
    assert "plosone-0318226-table2-age:beta" in seed.target_map()
    assert "frontiers-1520668-table2-f01:p_value" in seed.target_map()


def test_release_receipt_binds_complete_precommitted_chain_and_is_nonproduction() -> None:
    first = _release()
    second = _release()

    assert first.production_authorized is False
    assert first.sha256() == second.sha256()
    assert len(first.sha256()) == 64
    assert len(first.development_curve_evidence_sha256) == 64
    assert len(first.test_curve_evidence_sha256) == 64


def test_sampling_frame_threshold_grid_or_seed_manifest_drift_fails_closed() -> None:
    fixture = _workflow_fixture()
    drifted_frame = ExtractionSamplingFrame(
        papers=fixture["frame"].papers[:-1],
        source_manifest_sha256=fixture["frame"].source_manifest_sha256,
    )
    with pytest.raises(ValueError, match="sampling frame"):
        _release(frame=drifted_frame)

    drifted_grid = ExtractionThresholdGrid(
        (
            ("t-080", 0.80),
            ("t-090", 0.90),
            ("t-099", 0.99),
        )
    )
    with pytest.raises(ValueError, match="threshold grid"):
        _release(grid=drifted_grid)

    wrong_seed = replace(fixture["seed"], source_manifest_sha256="7" * 64)
    with pytest.raises(ValueError, match="seed manifest"):
        _release(seed=wrong_seed)

    changed_seed_target = replace(fixture["seed"].targets[0], key="se")
    changed_seed = replace(
        fixture["seed"],
        targets=(changed_seed_target, *fixture["seed"].targets[1:]),
    )
    with pytest.raises(ValueError, match="seed target universe"):
        _release(seed=changed_seed)

    wrong_seed_gold = replace(fixture["gold"], source_seed_manifest_sha256="8" * 64)
    with pytest.raises(ValueError, match="seed manifest"):
        _release(gold=wrong_seed_gold)


def test_gold_targets_must_belong_to_exact_precommitted_seed_universe() -> None:
    fixture = _workflow_fixture()
    outside = replace(fixture["gold"].targets[0], target_id="not-in-seed-universe")
    outside_gold = replace(
        fixture["gold"],
        targets=(outside, *fixture["gold"].targets[1:]),
    )
    with pytest.raises(ValueError, match="outside the precommitted seed target universe"):
        _release(gold=outside_gold)

    drifted = replace(fixture["gold"].targets[0], key="se")
    drifted_gold = replace(
        fixture["gold"],
        targets=(drifted, *fixture["gold"].targets[1:]),
    )
    with pytest.raises(ValueError, match="identity drifted from seed manifest"):
        _release(gold=drifted_gold)

    drifted_source = replace(
        fixture["gold"].targets[0],
        source=replace(fixture["gold"].targets[0].source, row="different-row"),
    )
    drifted_source_gold = replace(
        fixture["gold"],
        targets=(drifted_source, *fixture["gold"].targets[1:]),
    )
    with pytest.raises(ValueError, match="source locator drifted from seed manifest"):
        _release(gold=drifted_source_gold)


def test_review_protocol_and_gold_sampling_universe_are_precommitted() -> None:
    fixture = _workflow_fixture()
    wrong_protocol = replace(fixture["plan"], review_protocol_version="different-review-v2")
    with pytest.raises(ValueError, match="review protocol"):
        _release(plan=wrong_protocol)

    outside = replace(
        fixture["gold"].targets[0],
        paper_id="paper-outside-frame",
        article_family_id="family-outside-frame",
    )
    bad_gold = replace(
        fixture["gold"],
        targets=(outside, *fixture["gold"].targets[1:]),
    )
    with pytest.raises(ValueError, match="identity drifted from seed manifest"):
        _release(gold=bad_gold)


def test_split_lock_and_frozen_threshold_cannot_drift() -> None:
    fixture = _workflow_fixture()
    assignments = list(fixture["split_lock"].assignments)
    family_id, split = assignments[0]
    assignments[0] = (
        family_id,
        BenchmarkSplit.TEST if split is not BenchmarkSplit.TEST else BenchmarkSplit.DEVELOPMENT,
    )
    drifted_split = replace(fixture["split_lock"], assignments=tuple(assignments))
    with pytest.raises(ValueError, match="deterministic lock"):
        _release(split_lock=drifted_split)

    drifted_frozen = replace(fixture["frozen"], threshold=fixture["frozen"].threshold + 0.001)
    with pytest.raises(ValueError, match="threshold value"):
        _release(frozen=drifted_frozen)

    with pytest.raises(ValueError, match="DEVELOPMENT manifest"):
        _release(development_manifest=fixture["test_manifest"])


def test_selectivity_evidence_must_match_frozen_development_observations() -> None:
    fixture = _workflow_fixture()
    observations = list(_threshold_observations(fixture["development_manifest"]))
    observations[0] = _observation(
        fixture["development_manifest"],
        "t-080",
        0.80,
        accepted=len(fixture["development_manifest"].targets),
    )
    changed_evidence = ExtractionSelectivityEvidence(
        manifest=fixture["development_manifest"],
        observations=tuple(observations),
    )
    with pytest.raises(ValueError, match="different DEVELOPMENT observation set"):
        _release(development_curve_evidence=changed_evidence)


def test_release_rejects_selectivity_evidence_from_different_gold_context() -> None:
    fixture = _workflow_fixture()
    other_gold = replace(fixture["gold"], split_salt="other-release-context-v1")
    other_lock = other_gold.build_split_lock()
    other_test_manifest = ExtractionSplitManifest(
        other_gold,
        other_lock,
        BenchmarkSplit.TEST,
    )
    other_test_evidence = ExtractionSelectivityEvidence(
        manifest=other_test_manifest,
        observations=_threshold_observations(other_test_manifest),
    )
    other_test_lock = lock_test_evaluation(
        fixture["frozen"],
        test_manifest=other_test_manifest,
    )

    with pytest.raises(ValueError, match="release gold|release split lock"):
        _release(
            test_manifest=other_test_manifest,
            test_curve_evidence=other_test_evidence,
            test_lock=other_test_lock,
        )


def test_test_seal_and_evaluation_lock_must_bind_exact_frozen_chain() -> None:
    fixture = _workflow_fixture()
    drifted_test_lock = replace(fixture["test_lock"], frozen_threshold_sha256="f" * 64)
    with pytest.raises(ValueError, match="frozen DEVELOPMENT threshold"):
        _release(test_lock=drifted_test_lock)

    drifted_seal = replace(fixture["test_seal"], split_lock_sha256="2" * 64)
    with pytest.raises(ValueError, match="split lock"):
        _release(test_seal=drifted_seal)


def test_both_published_curves_must_use_precommitted_threshold_id_value_grid() -> None:
    fixture = _workflow_fixture()
    bad_development_observations = list(_threshold_observations(fixture["development_manifest"]))
    bad_development_observations[0] = replace(
        bad_development_observations[0],
        threshold=0.79,
    )
    bad_development_observations = tuple(bad_development_observations)
    bad_development_evidence = ExtractionSelectivityEvidence(
        manifest=fixture["development_manifest"],
        observations=bad_development_observations,
    )
    bad_frozen = select_development_threshold(
        bad_development_observations,
        policy=ExtractionThresholdPolicy(
            min_selective_coverage=0.0,
            min_accepted_full_accuracy=1.0,
            max_critical_family_wrong_accept_upper_bound=1.0,
        ),
        development_manifest=fixture["development_manifest"],
    )
    with pytest.raises(ValueError, match="DEVELOPMENT selectivity evidence"):
        _release(
            frozen=bad_frozen,
            development_curve_evidence=bad_development_evidence,
        )

    bad_test_observations = list(_threshold_observations(fixture["test_manifest"]))
    bad_test_observations[2] = replace(bad_test_observations[2], threshold_id="t-099")
    bad_test_evidence = ExtractionSelectivityEvidence(
        manifest=fixture["test_manifest"],
        observations=tuple(bad_test_observations),
    )
    with pytest.raises(ValueError, match="TEST selectivity evidence"):
        _release(test_curve_evidence=bad_test_evidence)


def test_plan_hash_binds_split_salt_seed_and_exact_sampling_source_bytes() -> None:
    frame = _sampling_frame()
    seed = _seed_manifest(frame)
    grid = ExtractionThresholdGrid((("t-1", 0.9),))
    base = build_extraction_evidence_plan(frame, seed, grid, split_salt="salt-a")
    changed_salt = build_extraction_evidence_plan(frame, seed, grid, split_salt="salt-b")
    changed_seed = build_extraction_evidence_plan(
        frame,
        replace(seed, source_manifest_sha256="7" * 64),
        grid,
        split_salt="salt-a",
    )
    changed_target = replace(seed.targets[0], row_label="different-row")
    changed_seed_universe = build_extraction_evidence_plan(
        frame,
        replace(seed, targets=(changed_target, *seed.targets[1:])),
        grid,
        split_salt="salt-a",
    )
    changed_bytes = build_extraction_evidence_plan(
        replace(frame, source_manifest_sha256="9" * 64),
        seed,
        grid,
        split_salt="salt-a",
    )

    assert base.sha256() != changed_salt.sha256()
    assert base.sha256() != changed_seed.sha256()
    assert base.sha256() != changed_seed_universe.sha256()
    assert base.sha256() != changed_bytes.sha256()


def test_release_receipt_cannot_be_marked_production_authorized() -> None:
    receipt = _release()
    with pytest.raises(ValueError, match="non-production"):
        replace(receipt, production_authorized=True)


def test_sampling_frame_model_rejects_wrong_status() -> None:
    with pytest.raises(ValueError, match="explicitly unlabeled"):
        ExtractionSamplingFrame(
            papers=(_paper(1),),
            source_manifest_sha256="a" * 64,
            status="gold",
        )


def test_evidence_plan_dataclass_rejects_non_hash_commitments() -> None:
    with pytest.raises(ValueError, match="sampling_frame_sha256"):
        ExtractionEvidencePlan(
            sampling_frame_sha256="not-a-hash",
            sampling_frame_source_manifest_sha256="a" * 64,
            source_seed_manifest_sha256="b" * 64,
            seed_target_universe_sha256="c" * 64,
            review_protocol_version="independent-double-review-v1",
            split_salt="salt",
            threshold_grid_sha256="d" * 64,
        )
