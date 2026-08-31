import pytest

from veritas.benchmark import BenchmarkSplit
from veritas.corpus import (
    AccessTier,
    ClaimExpectation,
    ClaimGroundTruth,
    CorpusManifest,
    CorpusPaper,
    GroundTruthBasis,
)


def _paper(paper_id: str, family: str) -> CorpusPaper:
    return CorpusPaper(
        paper_id=paper_id,
        article_family_id=family,
        doi=None,
        title=f"Paper {paper_id}",
        discipline="psychology",
        year=2025,
        source_url="https://example.org/paper",
        access_tier=AccessTier.PAPER_ONLY,
    )


def test_article_versions_share_one_split():
    manifest = CorpusManifest(
        papers=(_paper("preprint", "family-1"), _paper("journal", "family-1")),
        labels=(),
        split_salt="locked-salt",
    )
    assert manifest.split_for_paper("preprint") is manifest.split_for_paper("journal")
    assert manifest.split_for_paper("preprint") in set(BenchmarkSplit)


def test_split_lock_is_stable_to_paper_order_and_versions():
    first = CorpusManifest(
        papers=(
            _paper("preprint", "family-1"),
            _paper("journal", "family-1"),
            _paper("other", "family-2"),
        ),
        labels=(),
        split_salt="locked-salt",
    )
    second = CorpusManifest(
        papers=tuple(reversed(first.papers)),
        labels=(),
        split_salt="locked-salt",
    )
    lock_a = first.build_split_lock()
    lock_b = second.build_split_lock()
    assert lock_a.sha256() == lock_b.sha256()
    assert len(lock_a.assignments) == 2
    assert lock_a.split_for_family("family-1") is first.split_for_paper("preprint")
    lock_a.validate_manifest(first)


def test_split_lock_rejects_corpus_growth_without_explicit_relock():
    original = CorpusManifest(
        papers=(_paper("p1", "family-1"),),
        labels=(),
        split_salt="locked-salt",
    )
    lock = original.build_split_lock()
    expanded = CorpusManifest(
        papers=(_paper("p1", "family-1"), _paper("p2", "family-2")),
        labels=(),
        split_salt="locked-salt",
    )
    with pytest.raises(ValueError, match="article-family universe differs"):
        lock.validate_manifest(expanded)


def test_split_lock_rejects_changed_salt():
    manifest = CorpusManifest(
        papers=(_paper("p1", "family-1"),),
        labels=(),
        split_salt="locked-salt",
    )
    lock = manifest.build_split_lock()
    changed = CorpusManifest(
        papers=manifest.papers,
        labels=(),
        split_salt="different-salt",
    )
    with pytest.raises(ValueError, match="split_salt"):
        lock.validate_manifest(changed)


def test_natural_binary_label_requires_two_reviewers_and_adjudication():
    with pytest.raises(ValueError):
        ClaimGroundTruth(
            label_id="L1",
            paper_id="p1",
            object_id="table-1",
            detector_id="regression_consistency",
            expectation=ClaimExpectation.INCONSISTENT,
            applicable=True,
            basis=GroundTruthBasis.MANUAL_RECONSTRUCTION,
            evidence_note="independent reconstruction",
            reviewers=("r1",),
            adjudicated=False,
        )


def test_controlled_corruption_requires_manifest_hash():
    with pytest.raises(ValueError):
        ClaimGroundTruth(
            label_id="L1",
            paper_id="p1",
            object_id="table-1",
            detector_id="regression_consistency",
            expectation=ClaimExpectation.INCONSISTENT,
            applicable=True,
            basis=GroundTruthBasis.CONTROLLED_CORRUPTION,
            evidence_note="p-value overwritten",
        )


def test_corpus_hash_is_order_invariant():
    papers = (_paper("p1", "f1"), _paper("p2", "f2"))
    label = ClaimGroundTruth(
        label_id="L1",
        paper_id="p1",
        object_id="o1",
        detector_id="regression_consistency",
        expectation=ClaimExpectation.CONSISTENT,
        applicable=True,
        basis=GroundTruthBasis.MANUAL_RECONSTRUCTION,
        evidence_note="manually checked",
        reviewers=("r1", "r2"),
        adjudicated=True,
    )
    first = CorpusManifest(papers=papers, labels=(label,), split_salt="s")
    second = CorpusManifest(papers=tuple(reversed(papers)), labels=(label,), split_salt="s")
    assert first.sha256() == second.sha256()
