from dataclasses import replace

import pytest

from veritas.benchmark import BenchmarkSplit
from veritas.corpus import assign_article_family_split
from veritas.extraction_benchmark import ExtractionGoldTarget
from veritas.extraction_review import ExtractionGoldManifest
from veritas.extraction_test_seal import ExtractionTestSetSeal, seal_extraction_test_set
from veritas.ingestion import EvidenceKind
from veritas.models import SourceLocation

_SPLIT_SALT = "extraction-test-seal"
_SEED_SHA = "a" * 64
_REVIEW_SHA = "b" * 64


def _family_for(split: BenchmarkSplit) -> str:
    for index in range(10000):
        family = f"family-{index}"
        if assign_article_family_split(family, salt=_SPLIT_SALT) is split:
            return family
    raise AssertionError(f"failed to find deterministic family for split {split.value}")


def _gold_target(target_id: str, family: str) -> ExtractionGoldTarget:
    return ExtractionGoldTarget(
        target_id=target_id,
        paper_id=f"paper-{family}",
        article_family_id=family,
        object_type="RegressionResult",
        key="beta",
        kind=EvidenceKind.FIELD,
        accepted_normalized_values=("0.18",),
        source=SourceLocation(
            artifact_id=f"paper-{family}",
            page=2,
            table="Table 1",
            row="Treatment",
            column="Estimate",
        ),
        reviewers=("reviewer-a", "reviewer-b"),
        adjudicated=True,
        review_record_sha256=_REVIEW_SHA,
    )


def _manifest() -> ExtractionGoldManifest:
    test_family = _family_for(BenchmarkSplit.TEST)
    dev_family = _family_for(BenchmarkSplit.DEVELOPMENT)
    return ExtractionGoldManifest(
        targets=(
            _gold_target("test-target", test_family),
            _gold_target("dev-target", dev_family),
        ),
        split_salt=_SPLIT_SALT,
        source_seed_manifest_sha256=_SEED_SHA,
    )


def test_test_set_seal_contains_only_test_families_and_validates_exact_artifacts():
    manifest = _manifest()
    split_lock = manifest.build_split_lock()
    seal = seal_extraction_test_set(manifest, split_lock)
    assert seal.test_article_family_ids == (_family_for(BenchmarkSplit.TEST),)
    seal.validate(manifest, split_lock)


def test_test_set_seal_rejects_relocked_manifest_even_with_same_split_salt():
    manifest = _manifest()
    split_lock = manifest.build_split_lock()
    seal = seal_extraction_test_set(manifest, split_lock)

    changed = ExtractionGoldManifest(
        targets=manifest.targets,
        split_salt=manifest.split_salt,
        source_seed_manifest_sha256="c" * 64,
    )
    changed_lock = changed.build_split_lock()
    try:
        seal.validate(changed, changed_lock)
    except ValueError as exc:
        assert "gold manifest SHA-256" in str(exc)
    else:
        raise AssertionError("changed gold content must invalidate the TEST seal")


def test_test_set_seal_schema_and_membership_types_fail_closed():
    manifest = _manifest()
    seal = seal_extraction_test_set(manifest, manifest.build_split_lock())

    with pytest.raises(ValueError, match="schema_version"):
        replace(seal, schema_version=True)
    with pytest.raises(ValueError, match="schema_version"):
        replace(seal, schema_version=2)
    with pytest.raises(ValueError, match="non-empty tuple"):
        replace(seal, test_article_family_ids=[])
    with pytest.raises(ValueError, match="non-empty strings"):
        replace(seal, test_article_family_ids=("",))


def test_test_set_seal_rejects_noncanonical_direct_construction():
    with pytest.raises(ValueError, match="unique and sorted"):
        ExtractionTestSetSeal(
            gold_manifest_sha256="a" * 64,
            split_lock_sha256="b" * 64,
            test_article_family_ids=("family-b", "family-a"),
        )
