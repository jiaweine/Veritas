from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from veritas.benchmark import BenchmarkSplit
from veritas.corpus import AccessTier, CorpusPaper
from veritas.extraction_benchmark import (
    ExtractionBenchmarkReport,
    ExtractionGoldTarget,
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
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)
from veritas.extraction_review import ExtractionGoldManifest
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
    split_values = {split for _, split in split_lock.assignments}
    assert BenchmarkSplit.DEVELOPMENT in split_values
    assert BenchmarkSplit.TEST in split_values

    plan = build_extraction_evidence_plan(
        frame,
        grid,
        source_seed_manifest_sha256=_SEED_SHA,
        split_salt=split_salt,
    )
    development_manifest_sha256 = "c" * 64
    observations = (
        ExtractionThresholdObservation(
            "t-080",
            0.80,
            BenchmarkSplit.DEVELOPMENT,
            _report(coverage=0.90, accuracy=0.995, upper_bound=0.04),
        ),
        ExtractionThresholdObservation(
            "t-090",
            0.90,
            BenchmarkSplit.DEVELOPMENT,
            _report(coverage=0.82, accuracy=1.0, upper_bound=0.03),
        ),
        ExtractionThresholdObservation(
            "t-095",
            0.95,
            BenchmarkSplit.DEVELOPMENT,
            _report(coverage=0.70, accuracy=1.0, upper_bound=0.02),
        ),
    )
    frozen = select_development_threshold(
        observations,
        policy=ExtractionThresholdPolicy(),
        development_manifest_sha256=development_manifest_sha256,
    )
    test_manifest_sha256 = "d" * 64
    test_seal = seal_extraction_test_set(gold, split_lock)
    test_lock = lock_test_evaluation(frozen, test_manifest_sha256=test_manifest_sha256)
    curve_reports = tuple((observation.threshold, observation.report) for observation in observations)
    development_curve = build_extraction_selectivity_curve(curve_reports)
    test_curve = build_extraction_selectivity_curve(
        (
            (0.80, _report(coverage=0.88, accuracy=0.99, upper_bound=0.045)),
            (0.90, _report(coverage=0.79, accuracy=1.0, upper_bound=0.035)),
            (0.95, _report(coverage=0.68, accuracy=1.0, upper_bound=0.025)),
        )
    )
    return {
        "frame": frame,
        "seed": seed,
        "grid": grid,
        "plan": plan,
        "gold": gold,
        "split_lock": split_lock,
        "frozen": frozen,
        "development_manifest_sha256": development_manifest_sha256,
        "test_seal": test_seal,
        "test_lock": test_lock,
        "test_manifest_sha256": test_manifest_sha256,
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
        split_lock=fixture["split_lock"],
        frozen_threshold=fixture["frozen"],
        development_manifest_sha256=fixture["development_manifest_sha256"],
        test_seal=fixture["test_seal"],
        test_evaluation_lock=fixture["test_lock"],
        test_manifest_sha256=fixture["test_manifest_sha256"],
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
    assert len(seed.targets) == 20
    assert "plosone-0318226-table2-age:beta" in seed.target_map()
    assert "frontiers-1520668-table2-f01:p_value" in seed.target_map()


def test_release_receipt_binds_complete_precommitted_chain_and_is_nonproduction() -> None:
    first = _release()
    second = _release()

    assert first.production_authorized is False
    assert first.sha256() == second.sha256()
    assert len(first.sha256()) == 64


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
        _release(development_manifest_sha256="e" * 64)


def test_test_seal_and_evaluation_lock_must_bind_exact_frozen_chain() -> None:
    fixture = _workflow_fixture()
    drifted_test_lock = replace(fixture["test_lock"], frozen_threshold_sha256="f" * 64)
    with pytest.raises(ValueError, match="frozen DEVELOPMENT threshold"):
        _release(test_lock=drifted_test_lock)

    with pytest.raises(ValueError, match="TEST manifest"):
        _release(test_manifest_sha256="1" * 64)

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
    grid = ExtractionThresholdGrid((("t-1", 0.9),))
    base = build_extraction_evidence_plan(
        frame,
        grid,
        source_seed_manifest_sha256=_SEED_SHA,
        split_salt="salt-a",
    )
    changed_salt = build_extraction_evidence_plan(
        frame,
        grid,
        source_seed_manifest_sha256=_SEED_SHA,
        split_salt="salt-b",
    )
    changed_seed = build_extraction_evidence_plan(
        frame,
        grid,
        source_seed_manifest_sha256="7" * 64,
        split_salt="salt-a",
    )
    changed_bytes = build_extraction_evidence_plan(
        replace(frame, source_manifest_sha256="9" * 64),
        grid,
        source_seed_manifest_sha256=_SEED_SHA,
        split_salt="salt-a",
    )

    assert base.sha256() != changed_salt.sha256()
    assert base.sha256() != changed_seed.sha256()
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
            review_protocol_version="independent-double-review-v1",
            split_salt="salt",
            threshold_grid_sha256="c" * 64,
        )
