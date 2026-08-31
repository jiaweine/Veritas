import pytest

from veritas.extraction_review import (
    ExtractionAdjudication,
    ExtractionGoldManifest,
    ExtractionReviewSubmission,
    ExtractionReviewTarget,
    resolve_extraction_reviews,
)
from veritas.ingestion import EvidenceKind
from veritas.models import SourceLocation


def _target(target_id: str = "t1", family: str = "family-1") -> ExtractionReviewTarget:
    return ExtractionReviewTarget(
        target_id=target_id,
        paper_id=f"paper-{family}",
        article_family_id=family,
        object_type="RegressionResult",
        key="beta",
        kind=EvidenceKind.FIELD,
    )


def _source(*, row: str = "Treatment") -> SourceLocation:
    return SourceLocation(
        artifact_id="paper",
        page=5,
        table="Table 2",
        row=row,
        column="Estimate",
    )


def _submission(
    reviewer: str,
    *,
    value: str = "0.18",
    row: str = "Treatment",
    target_id: str = "t1",
) -> ExtractionReviewSubmission:
    return ExtractionReviewSubmission(
        target_id=target_id,
        reviewer_id=reviewer,
        accepted_normalized_values=(value,),
        source=_source(row=row),
        note="independent extraction",
    )


def test_two_agreeing_reviewers_create_review_bound_gold():
    record = resolve_extraction_reviews(
        _target(),
        (_submission("reviewer-a"), _submission("reviewer-b")),
    )
    assert record.adjudicated is False
    assert record.accepted_normalized_values == ("0.18",)
    assert len(record.sha256()) == 64

    gold = record.to_gold_target()
    assert gold.review_record_sha256 == record.sha256()
    assert gold.reviewers == ("reviewer-a", "reviewer-b")
    assert gold.adjudicated is True


def test_review_record_hash_is_invariant_to_submission_order():
    first = resolve_extraction_reviews(
        _target(),
        (_submission("reviewer-a"), _submission("reviewer-b")),
    )
    second = resolve_extraction_reviews(
        _target(),
        (_submission("reviewer-b"), _submission("reviewer-a")),
    )
    assert first.sha256() == second.sha256()


def test_disagreement_requires_independent_adjudication():
    with pytest.raises(ValueError, match="disagreement requires independent adjudication"):
        resolve_extraction_reviews(
            _target(),
            (_submission("reviewer-a", value="0.18"), _submission("reviewer-b", value="0.81")),
        )


def test_adjudicator_must_not_be_one_of_the_original_reviewers():
    adjudication = ExtractionAdjudication(
        target_id="t1",
        adjudicator_id="reviewer-a",
        accepted_normalized_values=("0.18",),
        source=_source(),
        note="resolved against PDF",
    )
    with pytest.raises(ValueError, match="adjudicator must be independent"):
        resolve_extraction_reviews(
            _target(),
            (_submission("reviewer-a", value="0.18"), _submission("reviewer-b", value="0.81")),
            adjudication=adjudication,
        )


def test_value_or_row_disagreement_can_be_adjudicated_by_third_reviewer():
    adjudication = ExtractionAdjudication(
        target_id="t1",
        adjudicator_id="reviewer-c",
        accepted_normalized_values=("0.18",),
        source=_source(),
        note="checked the publication table and selected the treatment row",
    )
    record = resolve_extraction_reviews(
        _target(),
        (
            _submission("reviewer-a", value="0.18"),
            _submission("reviewer-b", value="0.18", row="Control"),
        ),
        adjudication=adjudication,
    )
    assert record.adjudicated is True
    assert record.source.row == "Treatment"
    assert record.to_gold_target().review_record_sha256 == record.sha256()


def test_duplicate_reviewer_identity_is_rejected():
    with pytest.raises(ValueError, match="distinct reviewer ids"):
        resolve_extraction_reviews(
            _target(),
            (_submission("reviewer-a"), _submission("reviewer-a")),
        )


def test_locked_gold_manifest_requires_review_provenance_and_binds_split_lock():
    first = resolve_extraction_reviews(
        _target("t1", "family-1"),
        (
            _submission("reviewer-a", target_id="t1"),
            _submission("reviewer-b", target_id="t1"),
        ),
    ).to_gold_target()
    second = resolve_extraction_reviews(
        _target("t2", "family-2"),
        (
            _submission("reviewer-a", target_id="t2"),
            _submission("reviewer-b", target_id="t2"),
        ),
    ).to_gold_target()
    manifest = ExtractionGoldManifest(
        targets=(first, second),
        split_salt="v0.11-extraction-lock",
        source_seed_manifest_sha256="a" * 64,
    )
    lock = manifest.build_split_lock()
    assert lock.manifest_sha256 == manifest.sha256()
    assert {family for family, _ in lock.assignments} == {"family-1", "family-2"}


def test_locked_gold_manifest_rejects_legacy_gold_without_review_hash():
    record = resolve_extraction_reviews(
        _target(),
        (_submission("reviewer-a"), _submission("reviewer-b")),
    )
    legacy = record.to_gold_target()
    object.__setattr__(legacy, "review_record_sha256", None)
    with pytest.raises(ValueError, match="review_record_sha256"):
        ExtractionGoldManifest(
            targets=(legacy,),
            split_salt="v0.11-extraction-lock",
            source_seed_manifest_sha256="a" * 64,
        )
