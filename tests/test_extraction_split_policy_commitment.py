from __future__ import annotations

from dataclasses import replace

import pytest

from test_extraction_evidence_workflow import _release, _workflow_fixture


def test_evidence_plan_hash_binds_article_family_split_fractions() -> None:
    fixture = _workflow_fixture()
    plan = fixture["plan"]

    changed_train = replace(plan, train_fraction=0.55)
    changed_development = replace(plan, development_fraction=0.25)

    assert changed_train.sha256() != plan.sha256()
    assert changed_development.sha256() != plan.sha256()


def test_evidence_plan_rejects_invalid_split_fraction_types_and_test_mass() -> None:
    plan = _workflow_fixture()["plan"]

    with pytest.raises(ValueError, match="train_fraction"):
        replace(plan, train_fraction=True)
    with pytest.raises(ValueError, match="development_fraction"):
        replace(plan, development_fraction=float("nan"))
    with pytest.raises(ValueError, match="positive mass for the TEST split"):
        replace(plan, train_fraction=0.80, development_fraction=0.20)


def test_release_rejects_split_lock_recomputed_with_post_plan_fractions() -> None:
    fixture = _workflow_fixture()
    changed_train = fixture["gold"].build_split_lock(
        train_fraction=0.55,
        development_fraction=0.20,
    )
    with pytest.raises(ValueError, match="train fraction differs"):
        _release(split_lock=changed_train)

    changed_development = fixture["gold"].build_split_lock(
        train_fraction=0.60,
        development_fraction=0.25,
    )
    with pytest.raises(ValueError, match="development fraction differs"):
        _release(split_lock=changed_development)