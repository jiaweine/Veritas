from __future__ import annotations

import json
from pathlib import Path

from veritas.benchmark import binomial_upper_bound
from veritas.corpus import assign_article_family_split
from veritas.extraction_calibration import ExtractionThresholdPolicy
from veritas.extraction_evidence_workflow import (
    ExtractionThresholdGrid,
    build_extraction_evidence_plan,
    extraction_evidence_plan_payload,
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_v015_nonproduction_pilot_plan_rebuilds_from_exact_sources() -> None:
    root = _root()
    frame = load_extraction_sampling_frame(
        root / "benchmark/corpus/evidence_sampling_frame_v0.15.json"
    )
    seed = load_extraction_seed_manifest(
        root / "benchmark/extraction/evidence_seed_manifest_v0.15.json"
    )
    archived = json.loads(
        (root / "benchmark/extraction/evidence_plan_v0.15.json").read_text(encoding="utf-8")
    )

    grid = ExtractionThresholdGrid(
        points=(("nc-005", 0.005), ("nc-010", 0.01), ("nc-020", 0.02))
    )
    plan = build_extraction_evidence_plan(
        frame,
        seed,
        grid,
        review_protocol_version="independent-double-review-v1",
        split_salt="veritas-extraction-evidence-v0.15-01",
        train_fraction=0.55,
        development_fraction=0.25,
        benchmark_confidence=0.95,
    )

    assert extraction_evidence_plan_payload(plan, grid) == archived
    assert plan.sha256() == archived["plan_sha256"] == (
        "1718d57c2736260f9a49ebb844f9935df2f98bdefe8a1009f0293f9d737b9069"
    )
    assert archived["production_authorized"] is False
    assert [row["threshold_id"] for row in archived["threshold_grid"]] == [
        "nc-005",
        "nc-010",
        "nc-020",
    ]

    families = sorted({target.article_family_id for target in seed.targets})
    assignments = {
        family_id: assign_article_family_split(
            family_id,
            salt=plan.split_salt,
            train_fraction=plan.train_fraction,
            development_fraction=plan.development_fraction,
        ).value
        for family_id in families
    }
    assert sum(split == "train" for split in assignments.values()) == 1
    assert sum(split == "development" for split in assignments.values()) == 2
    assert sum(split == "test" for split in assignments.values()) == 1


def test_v015_pilot_policy_is_explicitly_nonproduction_and_power_bounded() -> None:
    root = _root()
    archived_plan = json.loads(
        (root / "benchmark/extraction/evidence_plan_v0.15.json").read_text(encoding="utf-8")
    )
    archived_policy = json.loads(
        (
            root / "benchmark/extraction/pretest_pilot_threshold_policy_v0.15.json"
        ).read_text(encoding="utf-8")
    )

    policy_payload = archived_policy["threshold_policy"]
    policy = ExtractionThresholdPolicy(
        min_selective_coverage=policy_payload["min_selective_coverage"],
        min_accepted_full_accuracy=policy_payload["min_accepted_full_accuracy"],
        max_critical_family_wrong_accept_upper_bound=(
            policy_payload["max_critical_family_wrong_accept_upper_bound"]
        ),
        schema_version=policy_payload["schema_version"],
    )
    default_policy = ExtractionThresholdPolicy()

    assert archived_policy["status"] == "frozen_nonproduction_pilot_threshold_policy"
    assert archived_policy["production_authorized"] is False
    assert archived_policy["bound_evidence_plan_sha256"] == archived_plan["plan_sha256"]
    assert archived_policy["benchmark_confidence"] == archived_plan["plan"]["benchmark_confidence"]
    assert policy.sha256() == archived_policy["threshold_policy_sha256"] == (
        "c8e9c7b65106460a49caa803b81b89eb2807a67a7cfb159f9cecb36b26a6fb55"
    )
    assert policy.max_critical_family_wrong_accept_upper_bound == 0.80
    assert default_policy.max_critical_family_wrong_accept_upper_bound == 0.05
    assert policy.max_critical_family_wrong_accept_upper_bound > (
        default_policy.max_critical_family_wrong_accept_upper_bound
    )

    zero_wrong = binomial_upper_bound(0, 2, confidence=0.95)
    one_wrong = binomial_upper_bound(1, 2, confidence=0.95)
    power = archived_policy["current_design_power"]
    assert zero_wrong == power["zero_wrong_accept_clopper_pearson_upper_bound"]
    assert one_wrong == power["one_wrong_accept_clopper_pearson_upper_bound"]
    assert zero_wrong <= policy.max_critical_family_wrong_accept_upper_bound
    assert one_wrong > policy.max_critical_family_wrong_accept_upper_bound
    assert power["zero_wrong_accept_satisfies_pilot_policy"] is True
    assert power["one_wrong_accept_satisfies_pilot_policy"] is False
    assert "does not establish a low population error rate" in archived_policy["interpretation"]
    assert "59 DEVELOPMENT families" in archived_policy["production_boundary"]
