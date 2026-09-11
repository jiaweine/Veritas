from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from veritas.benchmark import binomial_upper_bound
from veritas.corpus import assign_article_family_split
from veritas.extraction_evidence_workflow import (
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_v015_pretest_design_readiness_recomputes_current_identity_power_and_resolution() -> None:
    root = _root()
    readiness = json.loads(
        (root / "benchmark/extraction/pretest_design_readiness_v0.15.json").read_text(
            encoding="utf-8"
        )
    )
    frame_path = root / readiness["sampling_frame"]["path"]
    seed_path = root / readiness["seed_manifest"]["path"]

    frame_raw = frame_path.read_bytes()
    seed_raw = seed_path.read_bytes()
    frame = load_extraction_sampling_frame(frame_path)
    seed = load_extraction_seed_manifest(seed_path)

    assert readiness["status"] == "resolved_with_explicit_nonproduction_pilot_policy"
    assert readiness["production_authorized"] is False
    assert readiness["evidence_plan_frozen"] is True

    assert sha256(frame_raw).hexdigest() == readiness["sampling_frame"]["source_sha256"]
    assert frame.sha256() == readiness["sampling_frame"]["normalized_sha256"]
    assert sha256(seed_raw).hexdigest() == readiness["seed_manifest"]["source_sha256"]
    assert seed.sha256() == readiness["seed_manifest"]["target_universe_sha256"]
    assert len(seed.targets) == readiness["seed_manifest"]["target_count"] == 18

    families = sorted({target.article_family_id for target in seed.targets})
    assert len(families) == readiness["seed_manifest"]["article_family_count"] == 4

    split = readiness["frozen_split_design"]
    assert split["status"] == "frozen_nonproduction_pilot_plan"
    expected_assignments = {
        row["article_family_id"]: row["split"] for row in split["assignments"]
    }
    actual_assignments = {
        family_id: assign_article_family_split(
            family_id,
            salt=split["split_salt"],
            train_fraction=split["train_fraction"],
            development_fraction=split["development_fraction"],
        ).value
        for family_id in families
    }
    assert actual_assignments == expected_assignments

    counts = {
        name: sum(value == name for value in actual_assignments.values())
        for name in ("train", "development", "test")
    }
    assert counts["train"] == split["train_article_families"] == 1
    assert counts["development"] == split["development_article_families"] == 2
    assert counts["test"] == split["test_article_families"] == 1

    power = readiness["default_policy_power_check"]
    observed_upper = binomial_upper_bound(
        power["development_wrong_accept_families_assumed"],
        counts["development"],
        confidence=power["benchmark_confidence"],
    )
    assert observed_upper == power["zero_wrong_accept_clopper_pearson_upper_bound"]

    minimum = next(
        family_count
        for family_count in range(1, 10_000)
        if binomial_upper_bound(
            0,
            family_count,
            confidence=power["benchmark_confidence"],
        )
        <= power["max_critical_family_wrong_accept_upper_bound"]
    )
    assert minimum == power[
        "minimum_development_families_for_zero_wrong_accept_upper_bound_at_or_below_policy"
    ] == 59
    assert observed_upper > power["max_critical_family_wrong_accept_upper_bound"]
    assert power["satisfies_default_policy_floor"] is False

    resolution = readiness["resolution"]
    plan = json.loads((root / resolution["evidence_plan_path"]).read_text(encoding="utf-8"))
    policy = json.loads(
        (root / resolution["pilot_threshold_policy_path"]).read_text(encoding="utf-8")
    )
    assert resolution["evidence_plan_sha256"] == plan["plan_sha256"]
    assert resolution["pilot_threshold_policy_sha256"] == policy["threshold_policy_sha256"]
    assert policy["bound_evidence_plan_sha256"] == plan["plan_sha256"]
    assert policy["production_authorized"] is False
    assert policy["threshold_policy"]["max_critical_family_wrong_accept_upper_bound"] == 0.80
    assert "does not replace the default 0.05" in resolution["resolution_rule"]
    assert "Independently archive" in readiness["remaining_external_pretest_work"]
