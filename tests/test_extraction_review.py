from dataclasses import replace

import pytest

from veritas.extraction_review import (
    ExtractionAdjudication,
    ExtractionGoldManifest,
    ExtractionReviewSubmission,
    ExtractionReviewTarget,
    build_extraction_gold_manifest,
    resolve_extraction_reviews,
    validate_extraction_gold_review_records,
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


def _adjudication(
    *,
    target_id: str = "t1",
    adjudicator: str = "reviewer-c",
    value: str = "0.18",
    row: str = "Treatment",
) -> ExtractionAdjudication:
    return ExtractionAdjudication(
        target_id=target_id,
        adjudicator_id=adjudicator,
        accepted_normalized_values=(value,),
        source=_source(row=row),
        note="independently checked the publication source",
    )


def _record(target_id: str = "t1", family: str = "family-1"):
    return resolve_extraction_reviews(
        _target(target_id, family),
        (
            _submission("reviewer-a", target_id=target_id),
            _submission("reviewer-b", target_id=target_id),
        ),
        adjudication=_adjudication(target_id=target_id),
    )


def test_two_agreeing_reviewers_create_review_record_but_not_locked_gold():
    record = resolve_extraction_reviews(
        _target(),
        (_submission("reviewer-a"), _submission("reviewer-b")),
    )
    assert record.adjudicated is False
    assert record.accepted_normalized_values == ("0.18",)
    assert len(record.sha256()) == 64

    with pytest.raises(ValueError, match="requires independent adjudication"):
        record.to_gold_target()


def test_agreeing_reviewers_can_be_independently_adjudicated_for_locked_gold():
    record = _record()
    assert record.adjudicated is True

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
    with pytest.raises(ValueError, match="adjudicator must be independent"):
        resolve_extraction_reviews(
            _target(),
            (_submission("reviewer-a", value="0.18"), _submission("reviewer-b", value="0.81")),
            adjudication=_adjudication(adjudicator="reviewer-a"),
        )


def test_value_or_row_disagreement_can_be_adjudicated_by_third_reviewer():
    record = resolve_extraction_reviews(
        _target(),
        (
            _submission("reviewer-a", value="0.18"),
            _submission("reviewer-b", value="0.18", row="Control"),
        ),
        adjudication=_adjudication(),
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


def test_locked_gold_manifest_is_built_and_verified_from_review_records():
    first = _record("t1", "family-1")
    second = _record("t2", "family-2")
    records = (first, second)
    manifest = build_extraction_gold_manifest(
        records,
        split_salt="v0.11-extraction-lock",
        source_seed_manifest_sha256="a" * 64,
    )
    validate_extraction_gold_review_records(manifest, records)

    lock = manifest.build_split_lock()
    assert lock.manifest_sha256 == manifest.sha256()
    assert {family for family, _ in lock.assignments} == {"family-1", "family-2"}


def test_gold_review_validation_rejects_forged_hash_or_missing_record():
    record = _record()
    manifest = build_extraction_gold_manifest(
        (record,),
        split_salt="v0.11-extraction-lock",
        source_seed_manifest_sha256="a" * 64,
    )
    forged_target = replace(manifest.targets[0], review_record_sha256="f" * 64)
    forged_manifest = replace(manifest, targets=(forged_target,))

    with pytest.raises(ValueError, match="differs from bound review record"):
        validate_extraction_gold_review_records(forged_manifest, (record,))
    with pytest.raises(ValueError, match="requires review records"):
        validate_extraction_gold_review_records(manifest, ())


def test_locked_gold_manifest_rejects_legacy_gold_without_review_hash():
    record = _record()
    legacy = record.to_gold_target()
    object.__setattr__(legacy, "review_record_sha256", None)
    with pytest.raises(ValueError, match="review_record_sha256"):
        ExtractionGoldManifest(
            targets=(legacy,),
            split_salt="v0.11-extraction-lock",
            source_seed_manifest_sha256="a" * 64,
        )