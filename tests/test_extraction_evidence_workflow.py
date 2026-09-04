from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from veritas.benchmark import BenchmarkSplit
from veritas.corpus import AccessTier, CorpusPaper
from veritas.extraction import ExtractionDecision
from veritas.extraction_benchmark import (
    ExtractionBenchmarkReport,
    ExtractionTargetOutcome,
    build_extraction_benchmark_report_from_outcomes,
    build_extraction_selectivity_curve,
)
from veritas.extraction_calibration import (
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
    build_extraction_split_target_manifest,
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)
from veritas.extraction_review import (
    ExtractionAdjudication,
    ExtractionReviewSubmission,
    ExtractionReviewTarget,
    build_extraction_gold_manifest,
    resolve_extraction_reviews,
)
from veritas.extraction_review_packet import ExtractionReviewPacketTarget
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


def _sampling_frame(count: int = 24) -> ExtractionSamplingFrame:
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


def _review_records(frame: ExtractionSamplingFrame):
    records = []
    for index, paper in enumerate(frame.papers):
        target_id = f"target-{index:02d}"
        value = f"{index / 100:.2f}"
        source = SourceLocation(
            artifact_id=paper.paper_id,
            page=2,
            table="Table 1",
            row=f"row-{index}",
            column="beta",
        )
        target = ExtractionReviewTarget(
            target_id=target_id,
            paper_id=paper.paper_id,
            article_family_id=paper.article_family_id,
            object_type="RegressionResult",
            key="beta",
            kind=EvidenceKind.FIELD,
        )
        submissions = tuple(
            ExtractionReviewSubmission(
                target_id=target_id,
                reviewer_id=reviewer_id,
                accepted_normalized_values=(value,),
                source=source,
                note="independent synthetic workflow review fixture",
            )
            for reviewer_id in ("reviewer-a", "reviewer-b")
        )
        adjudication = ExtractionAdjudication(
            target_id=target_id,
            adjudicator_id="reviewer-c",
            accepted_normalized_values=(value,),
            source=source,
            note="independent synthetic workflow adjudication fixture",
        )
        records.append(
            resolve_extraction_reviews(
                target,
                submissions,
                adjudication=adjudication,
            )
        )
    return tuple(records)


def _report(*, coverage: float, accuracy: float, upper_bound: float) -> ExtractionBenchmarkReport:
    return ExtractionBenchmarkReport(
        targets=10,
        accepted=8,
        fully_correct_accepts=8,
        wrong_accepts=0,
        abstentions=2,
        conflicts=0,
        domain_shifts=0,
        selective_coverage=coverage,
        accepted_full_accuracy=accuracy,
        wrong_accept_rate=0.0,
        accepted_value_accuracy=accuracy,
        accepted_source_accuracy=accuracy,
        field_targets=10,
        accepted_field_targets=8,
        accepted_field_value_accuracy=accuracy,
        table_row_targets=10,
        accepted_table_row_targets=8,
        accepted_table_row_identity_accuracy=accuracy,
        semantic_gate_targets=0,
        accepted_semantic_gate_targets=0,
        accepted_semantic_gate_accuracy=0.0,
        critical_article_families=8,
        critical_wrong_accept_families=0,
        critical_family_wrong_accept_rate=0.0,
        critical_family_wrong_accept_upper_bound=upper_bound,
        outcomes=(),
    )


def _gold_subset(gold, target_ids):
    target_ids = set(target_ids)
    return tuple(target for target in gold.targets if target.target_id in target_ids)


def _bound_report(gold, accepted_count: int, *, confidence: float = 0.95):
    outcomes = []
    for index, target in enumerate(gold):
        accepted = index < accepted_count
        outcomes.append(
            ExtractionTargetOutcome(
                target_id=target.target_id,
                paper_id=target.paper_id,
                article_family_id=target.article_family_id,
                kind=target.kind,
                critical_for_hard_audit=target.critical_for_hard_audit,
                decision=(ExtractionDecision.ACCEPT if accepted else ExtractionDecision.ABSTAIN),
                accepted=accepted,
                value_correct=True if accepted else None,
                source_correct=True if accepted else None,
                page_correct=True if accepted else None,
                display_item_correct=True if accepted else None,
                row_correct=True if accepted else None,
                column_correct=True if accepted else None,
            )
        )
    return build_extraction_benchmark_report_from_outcomes(
        gold,
        outcomes,
        confidence=confidence,
    )


def _observation_set(gold, *, split: BenchmarkSplit, confidence: float = 0.95):
    count = len(gold)
    accepted_counts = (count, max(count - 1, 0), max(count - 2, 0))
    return tuple(
        ExtractionThresholdObservation(
            threshold_id,
            threshold,
            split,
            _bound_report(gold, accepted_count, confidence=confidence),
        )
        for (threshold_id, threshold), accepted_count in zip(
            (("t-080", 0.80), ("t-090", 0.90), ("t-095", 0.95)),
            accepted_counts,
            strict=True,
        )
    )


def _workflow_fixture():
    frame = _sampling_frame()
    seed = _seed_manifest(frame)
    grid = ExtractionThresholdGrid(
        (("t-080", 0.80), ("t-090", 0.90), ("t-095", 0.95))
    )
    split_salt = "release-workflow-v1"
    review_records = _review_records(frame)
    gold = build_extraction_gold_manifest(
        review_records,
        split_salt=split_salt,
        source_seed_manifest_sha256=_SEED_SHA,
    )
    split_lock = gold.build_split_lock()
    split_values = {split for _, split in split_lock.assignments}
    assert BenchmarkSplit.DEVELOPMENT in split_values
    assert BenchmarkSplit.TEST in split_values

    plan = build_extraction_evidence_plan(
        frame,
        seed,
        grid,
        split_salt=split_salt,
        benchmark_confidence=0.95,
    )
    development_manifest = build_extraction_split_target_manifest(
        gold,
        split_lock,
        split=BenchmarkSplit.DEVELOPMENT,
    )
    test_manifest = build_extraction_split_target_manifest(
        gold,
        split_lock,
        split=BenchmarkSplit.TEST,
    )
    development_gold = _gold_subset(gold, development_manifest.target_ids)
    test_gold = _gold_subset(gold, test_manifest.target_ids)
    observations = _observation_set(
        development_gold,
        split=BenchmarkSplit.DEVELOPMENT,
        confidence=plan.benchmark_confidence,
    )
    test_observations = _observation_set(
        test_gold,
        split=BenchmarkSplit.TEST,
        confidence=plan.benchmark_confidence,
    )
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.0,
        min_accepted_full_accuracy=0.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    frozen = select_development_threshold(
        observations,
        policy=policy,
        development_manifest_sha256=development_manifest.sha256(),
    )
    test_seal = seal_extraction_test_set(gold, split_lock)
    test_lock = lock_test_evaluation(frozen, test_manifest_sha256=test_manifest.sha256())
    development_curve = build_extraction_selectivity_curve(
        tuple((observation.threshold, observation.report) for observation in observations)
    )
    test_curve = build_extraction_selectivity_curve(
        tuple((observation.threshold, observation.report) for observation in test_observations)
    )
    return {
        "frame": frame,
        "seed": seed,
        "grid": grid,
        "plan": plan,
        "review_records": review_records,
        "gold": gold,
        "split_lock": split_lock,
        "development_manifest": development_manifest,
        "test_manifest": test_manifest,
        "development_gold": development_gold,
        "test_gold": test_gold,
        "policy": policy,
        "observations": observations,
        "test_observations": test_observations,
        "frozen": frozen,
        "test_seal": test_seal,
        "test_lock": test_lock,
        "development_curve": development_curve,
        "test_curve": test_curve,
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
        review_records=fixture["review_records"],
        split_lock=fixture["split_lock"],
        threshold_policy=fixture["policy"],
        development_observations=fixture["observations"],
        test_observations=fixture["test_observations"],
        frozen_threshold=fixture["frozen"],
        test_seal=fixture["test_seal"],
        test_evaluation_lock=fixture["test_lock"],
        development_curve=fixture["development_curve"],
        test_curve=fixture["test_curve"],
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


def test_split_target_manifests_are_deterministic_subsets_of_locked_gold() -> None:
    fixture = _workflow_fixture()
    development = fixture["development_manifest"]
    test = fixture["test_manifest"]
    assert development.split is BenchmarkSplit.DEVELOPMENT
    assert test.split is BenchmarkSplit.TEST
    assert development.gold_manifest_sha256 == fixture["gold"].sha256()
    assert test.gold_manifest_sha256 == fixture["gold"].sha256()
    assert development.split_lock_sha256 == fixture["split_lock"].sha256()
    assert test.split_lock_sha256 == fixture["split_lock"].sha256()
    assert set(development.article_family_ids).isdisjoint(test.article_family_ids)
    assert set(development.target_ids).isdisjoint(test.target_ids)
    assert len(development.sha256()) == 64
    assert len(test.sha256()) == 64


def test_release_receipt_binds_complete_precommitted_chain_and_is_nonproduction() -> None:
    fixture = _workflow_fixture()
    first = _release()
    second = _release()
    assert first.production_authorized is False
    assert first.development_manifest_sha256 == fixture["development_manifest"].sha256()
    assert first.test_manifest_sha256 == fixture["test_manifest"].sha256()
    assert len(first.development_observations_sha256) == 64
    assert len(first.test_observations_sha256) == 64
    assert first.development_observations_sha256 != first.test_observations_sha256
    assert first.sha256() == second.sha256()
    assert len(first.sha256()) == 64


def test_release_requires_concrete_review_records_not_only_gold_hash_fields() -> None:
    fixture = _workflow_fixture()
    forged_target = replace(fixture["gold"].targets[0], review_record_sha256="f" * 64)
    forged_gold = replace(
        fixture["gold"],
        targets=(forged_target, *fixture["gold"].targets[1:]),
    )
    with pytest.raises(ValueError, match="bound review record"):
        _release(gold=forged_gold)
    with pytest.raises(ValueError, match="target membership differs"):
        _release(review_records=fixture["review_records"][1:])


def test_release_recomputes_development_policy_and_threshold_selection() -> None:
    fixture = _workflow_fixture()
    changed_policy = ExtractionThresholdPolicy(
        min_selective_coverage=0.25,
        min_accepted_full_accuracy=0.0,
        max_critical_family_wrong_accept_upper_bound=1.0,
    )
    with pytest.raises(ValueError, match="deterministic DEVELOPMENT selection"):
        _release(policy=changed_policy)

    forged_frozen = replace(fixture["frozen"], policy_sha256="f" * 64)
    with pytest.raises(ValueError, match="deterministic DEVELOPMENT selection"):
        _release(frozen=forged_frozen)

    drifted_observation = replace(fixture["observations"][0], threshold=0.81)
    with pytest.raises(ValueError, match="threshold value differs"):
        _release(observations=(drifted_observation, *fixture["observations"][1:]))


def test_release_rejects_report_membership_or_aggregate_forgery() -> None:
    fixture = _workflow_fixture()
    wrong_membership = replace(
        fixture["observations"][0],
        report=fixture["test_observations"][0].report,
    )
    with pytest.raises(ValueError, match="outcome membership differs"):
        _release(observations=(wrong_membership, *fixture["observations"][1:]))

    forged_report = replace(
        fixture["observations"][0].report,
        accepted=fixture["observations"][0].report.accepted + 1,
    )
    forged_observation = replace(fixture["observations"][0], report=forged_report)
    with pytest.raises(ValueError, match="aggregates differ"):
        _release(observations=(forged_observation, *fixture["observations"][1:]))


def test_development_and_test_curves_must_be_derived_from_bound_observations() -> None:
    fixture = _workflow_fixture()
    development_points = list(fixture["development_curve"].points)
    development_points[0] = replace(
        development_points[0],
        selective_coverage=max(0.0, development_points[0].selective_coverage - 0.01),
    )
    changed_development = replace(
        fixture["development_curve"],
        points=tuple(development_points),
    )
    with pytest.raises(ValueError, match="bound DEVELOPMENT observations"):
        _release(development_curve=changed_development)

    test_points = list(fixture["test_curve"].points)
    test_points[0] = replace(
        test_points[0],
        selective_coverage=max(0.0, test_points[0].selective_coverage - 0.01),
    )
    changed_test = replace(fixture["test_curve"], points=tuple(test_points))
    with pytest.raises(ValueError, match="bound TEST observations"):
        _release(test_curve=changed_test)


def test_benchmark_confidence_is_precommitted_and_validated() -> None:
    frame = _sampling_frame()
    seed = _seed_manifest(frame)
    grid = ExtractionThresholdGrid((("t-1", 0.9),))
    first = build_extraction_evidence_plan(
        frame,
        seed,
        grid,
        split_salt="confidence-lock",
        benchmark_confidence=0.95,
    )
    second = build_extraction_evidence_plan(
        frame,
        seed,
        grid,
        split_salt="confidence-lock",
        benchmark_confidence=0.90,
    )
    assert first.sha256() != second.sha256()
    with pytest.raises(ValueError, match="benchmark_confidence"):
        replace(first, benchmark_confidence=True)
    with pytest.raises(ValueError, match="benchmark_confidence"):
        replace(first, benchmark_confidence=float("nan"))


def test_sampling_frame_threshold_grid_or_seed_manifest_drift_fails_closed() -> None:
    fixture = _workflow_fixture()
    drifted_frame = ExtractionSamplingFrame(
        papers=fixture["frame"].papers[:-1],
        source_manifest_sha256=fixture["frame"].source_manifest_sha256,
    )
    with pytest.raises(ValueError, match="sampling frame"):
        _release(frame=drifted_frame)

    drifted_grid = ExtractionThresholdGrid(
        (("t-080", 0.80), ("t-090", 0.90), ("t-099", 0.99))
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
    with pytest.raises(ValueError, match="deterministic DEVELOPMENT selection"):
        _release(frozen=drifted_frozen)

    wrong_development_manifest = replace(
        fixture["frozen"],
        development_manifest_sha256="e" * 64,
    )
    with pytest.raises(ValueError, match="deterministic DEVELOPMENT selection"):
        _release(frozen=wrong_development_manifest)


def test_test_seal_and_evaluation_lock_must_bind_exact_frozen_chain() -> None:
    fixture = _workflow_fixture()
    drifted_test_lock = replace(fixture["test_lock"], frozen_threshold_sha256="f" * 64)
    with pytest.raises(ValueError, match="frozen DEVELOPMENT threshold"):
        _release(test_lock=drifted_test_lock)

    wrong_test_manifest = replace(fixture["test_lock"], test_manifest_sha256="1" * 64)
    with pytest.raises(ValueError, match="TEST manifest"):
        _release(test_lock=wrong_test_manifest)

    drifted_seal = replace(fixture["test_seal"], split_lock_sha256="2" * 64)
    with pytest.raises(ValueError, match="split lock"):
        _release(test_seal=drifted_seal)


def test_both_published_curves_must_use_precommitted_threshold_grid() -> None:
    bad_curve = build_extraction_selectivity_curve(
        (
            (0.80, _report(coverage=0.8, accuracy=1.0, upper_bound=0.04)),
            (0.90, _report(coverage=0.7, accuracy=1.0, upper_bound=0.03)),
        )
    )
    with pytest.raises(ValueError, match="DEVELOPMENT selectivity curve"):
        _release(development_curve=bad_curve)
    with pytest.raises(ValueError, match="TEST selectivity curve"):
        _release(test_curve=bad_curve)


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
