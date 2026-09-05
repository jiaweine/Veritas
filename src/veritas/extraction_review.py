from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256

from .corpus import ArticleFamilySplitLock, assign_article_family_split
from .extraction_benchmark import ExtractionGoldTarget
from .ingestion import EvidenceKind
from .models import SourceLocation

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExtractionReviewTarget:
    target_id: str
    paper_id: str
    article_family_id: str
    object_type: str
    key: str
    kind: EvidenceKind
    critical_for_hard_audit: bool = True

    def __post_init__(self) -> None:
        for label, value in (
            ("target_id", self.target_id),
            ("paper_id", self.paper_id),
            ("article_family_id", self.article_family_id),
            ("object_type", self.object_type),
            ("key", self.key),
        ):
            _require_nonempty_string(value, label=label)
        if not isinstance(self.kind, EvidenceKind):
            raise TypeError("kind must be an EvidenceKind")
        if type(self.critical_for_hard_audit) is not bool:
            raise TypeError("critical_for_hard_audit must be boolean")


@dataclass(frozen=True)
class ExtractionReviewSubmission:
    target_id: str
    reviewer_id: str
    accepted_normalized_values: tuple[str, ...]
    source: SourceLocation
    note: str = ""

    def __post_init__(self) -> None:
        _require_nonempty_string(self.target_id, label="target_id")
        _require_nonempty_string(self.reviewer_id, label="reviewer_id")
        _require_nonempty_string_tuple(
            self.accepted_normalized_values,
            label="accepted_normalized_values",
        )
        if not isinstance(self.source, SourceLocation):
            raise TypeError("source must be a SourceLocation")
        if not isinstance(self.note, str):
            raise TypeError("note must be a string")


@dataclass(frozen=True)
class ExtractionAdjudication:
    target_id: str
    adjudicator_id: str
    accepted_normalized_values: tuple[str, ...]
    source: SourceLocation
    note: str

    def __post_init__(self) -> None:
        _require_nonempty_string(self.target_id, label="target_id")
        _require_nonempty_string(self.adjudicator_id, label="adjudicator_id")
        _require_nonempty_string_tuple(
            self.accepted_normalized_values,
            label="accepted_normalized_values",
        )
        if not isinstance(self.source, SourceLocation):
            raise TypeError("source must be a SourceLocation")
        _require_nonempty_string(self.note, label="adjudication note")


@dataclass(frozen=True)
class ExtractionReviewRecord:
    target: ExtractionReviewTarget
    submissions: tuple[ExtractionReviewSubmission, ...]
    accepted_normalized_values: tuple[str, ...]
    source: SourceLocation
    adjudication: ExtractionAdjudication | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version, label="review record")
        if not isinstance(self.target, ExtractionReviewTarget):
            raise TypeError("review record target must be an ExtractionReviewTarget")
        if not isinstance(self.submissions, tuple) or any(
            not isinstance(submission, ExtractionReviewSubmission)
            for submission in self.submissions
        ):
            raise TypeError("review record submissions must be ExtractionReviewSubmission values")
        if len(self.submissions) < 2:
            raise ValueError("review record requires at least two independent submissions")
        _require_nonempty_string_tuple(
            self.accepted_normalized_values,
            label="accepted_normalized_values",
        )
        if not isinstance(self.source, SourceLocation):
            raise TypeError("review record source must be a SourceLocation")
        if self.adjudication is not None and not isinstance(
            self.adjudication, ExtractionAdjudication
        ):
            raise TypeError("review record adjudication must be an ExtractionAdjudication or None")

        reviewers = [submission.reviewer_id for submission in self.submissions]
        if len(set(reviewers)) != len(reviewers):
            raise ValueError("review submissions must use distinct reviewer ids")
        if any(submission.target_id != self.target.target_id for submission in self.submissions):
            raise ValueError("review submissions must reference the review target")

        value_sets = {
            _normalized_values_key(submission.accepted_normalized_values)
            for submission in self.submissions
        }
        source_keys = {_source_identity_key(submission.source) for submission in self.submissions}
        consensus = len(value_sets) == 1 and len(source_keys) == 1

        if self.adjudication is None:
            if not consensus:
                raise ValueError("review disagreement requires independent adjudication")
            expected_values = _canonical_values(self.submissions[0].accepted_normalized_values)
            expected_source = self.submissions[0].source
            if _canonical_values(self.accepted_normalized_values) != expected_values:
                raise ValueError("review record values differ from reviewer consensus")
            if _source_identity_key(self.source) != _source_identity_key(expected_source):
                raise ValueError("review record source differs from reviewer consensus")
            return

        if self.adjudication.target_id != self.target.target_id:
            raise ValueError("adjudication must reference the review target")
        if self.adjudication.adjudicator_id in set(reviewers):
            raise ValueError("adjudicator must be independent of the original reviewers")
        if _canonical_values(self.accepted_normalized_values) != _canonical_values(
            self.adjudication.accepted_normalized_values
        ):
            raise ValueError("review record values differ from adjudication")
        if _source_identity_key(self.source) != _source_identity_key(self.adjudication.source):
            raise ValueError("review record source differs from adjudication")

    @property
    def reviewers(self) -> tuple[str, ...]:
        return tuple(submission.reviewer_id for submission in self.submissions)

    @property
    def adjudicated(self) -> bool:
        return self.adjudication is not None

    def sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "target": _review_target_payload(self.target),
            "submissions": [
                _submission_payload(submission)
                for submission in sorted(self.submissions, key=lambda item: item.reviewer_id)
            ],
            "accepted_normalized_values": sorted(self.accepted_normalized_values),
            "source": asdict(self.source),
            "adjudication": (
                _adjudication_payload(self.adjudication) if self.adjudication is not None else None
            ),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()

    def to_gold_target(self) -> ExtractionGoldTarget:
        if self.adjudication is None:
            raise ValueError("locked gold promotion requires independent adjudication")
        return ExtractionGoldTarget(
            target_id=self.target.target_id,
            paper_id=self.target.paper_id,
            article_family_id=self.target.article_family_id,
            object_type=self.target.object_type,
            key=self.target.key,
            kind=self.target.kind,
            accepted_normalized_values=self.accepted_normalized_values,
            source=self.source,
            critical_for_hard_audit=self.target.critical_for_hard_audit,
            reviewers=self.reviewers,
            adjudicated=True,
            review_record_sha256=self.sha256(),
        )


@dataclass(frozen=True)
class ExtractionGoldManifest:
    targets: tuple[ExtractionGoldTarget, ...]
    split_salt: str
    source_seed_manifest_sha256: str
    review_protocol_version: str = "independent-double-review-v1"
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version, label="gold manifest")
        if not isinstance(self.targets, tuple) or not self.targets:
            raise ValueError("gold manifest requires a non-empty tuple of targets")
        if any(not isinstance(target, ExtractionGoldTarget) for target in self.targets):
            raise TypeError("gold manifest targets must be ExtractionGoldTarget values")
        target_ids = [target.target_id for target in self.targets]
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("gold manifest target_id values must be unique")
        _require_nonempty_string(self.split_salt, label="split_salt")
        _require_nonempty_string(self.review_protocol_version, label="review_protocol_version")
        if not isinstance(self.source_seed_manifest_sha256, str) or not _SHA256_RE.fullmatch(
            self.source_seed_manifest_sha256
        ):
            raise ValueError("source_seed_manifest_sha256 must be a lowercase SHA-256 hex digest")
        for target in self.targets:
            if not target.review_record_sha256 or not _SHA256_RE.fullmatch(target.review_record_sha256):
                raise ValueError("locked gold targets require review_record_sha256 provenance")
            if len(set(target.reviewers)) < 2 or not target.adjudicated:
                raise ValueError("locked gold targets require independent double review and adjudication status")

    @property
    def article_family_ids(self) -> tuple[str, ...]:
        return tuple(sorted({target.article_family_id for target in self.targets}))

    def sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "split_salt": self.split_salt,
            "source_seed_manifest_sha256": self.source_seed_manifest_sha256,
            "review_protocol_version": self.review_protocol_version,
            "targets": [
                _gold_target_payload(target)
                for target in sorted(self.targets, key=lambda item: item.target_id)
            ],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()

    def build_split_lock(
        self,
        *,
        train_fraction: float = 0.60,
        development_fraction: float = 0.20,
    ) -> ArticleFamilySplitLock:
        assignments = tuple(
            (
                family_id,
                assign_article_family_split(
                    family_id,
                    salt=self.split_salt,
                    train_fraction=train_fraction,
                    development_fraction=development_fraction,
                ),
            )
            for family_id in self.article_family_ids
        )
        return ArticleFamilySplitLock(
            manifest_sha256=self.sha256(),
            split_salt=self.split_salt,
            train_fraction=train_fraction,
            development_fraction=development_fraction,
            assignments=assignments,
        )


def build_extraction_gold_manifest(
    review_records: tuple[ExtractionReviewRecord, ...] | list[ExtractionReviewRecord],
    *,
    split_salt: str,
    source_seed_manifest_sha256: str,
    review_protocol_version: str = "independent-double-review-v1",
) -> ExtractionGoldManifest:
    records = tuple(review_records)
    if not records:
        raise ValueError("locked gold requires at least one review record")
    if any(not isinstance(record, ExtractionReviewRecord) for record in records):
        raise TypeError("locked gold review records must be ExtractionReviewRecord values")
    targets = tuple(record.to_gold_target() for record in records)
    return ExtractionGoldManifest(
        targets=targets,
        split_salt=split_salt,
        source_seed_manifest_sha256=source_seed_manifest_sha256,
        review_protocol_version=review_protocol_version,
    )


def validate_extraction_gold_review_records(
    gold_manifest: ExtractionGoldManifest,
    review_records: tuple[ExtractionReviewRecord, ...] | list[ExtractionReviewRecord],
) -> None:
    records = tuple(review_records)
    if not records:
        raise ValueError("locked gold validation requires review records")
    if any(not isinstance(record, ExtractionReviewRecord) for record in records):
        raise TypeError("locked gold validation requires ExtractionReviewRecord values")
    record_by_id = {record.target.target_id: record for record in records}
    if len(record_by_id) != len(records):
        raise ValueError("review records must use unique target ids")
    gold_by_id = {target.target_id: target for target in gold_manifest.targets}
    if set(record_by_id) != set(gold_by_id):
        missing = tuple(sorted(set(gold_by_id) - set(record_by_id)))
        extra = tuple(sorted(set(record_by_id) - set(gold_by_id)))
        raise ValueError(
            "gold/review-record target membership differs: "
            f"missing_records={missing!r}, extra_records={extra!r}"
        )
    for target_id in sorted(gold_by_id):
        derived = record_by_id[target_id].to_gold_target()
        if _gold_target_payload(derived) != _gold_target_payload(gold_by_id[target_id]):
            raise ValueError(f"gold target differs from bound review record: {target_id!r}")


def resolve_extraction_reviews(
    target: ExtractionReviewTarget,
    submissions: tuple[ExtractionReviewSubmission, ...] | list[ExtractionReviewSubmission],
    *,
    adjudication: ExtractionAdjudication | None = None,
) -> ExtractionReviewRecord:
    if not isinstance(target, ExtractionReviewTarget):
        raise TypeError("target must be an ExtractionReviewTarget")
    submissions = tuple(submissions)
    if any(not isinstance(submission, ExtractionReviewSubmission) for submission in submissions):
        raise TypeError("submissions must contain ExtractionReviewSubmission values")
    if len(submissions) < 2:
        raise ValueError("at least two independent review submissions are required")
    if adjudication is not None and not isinstance(adjudication, ExtractionAdjudication):
        raise TypeError("adjudication must be an ExtractionAdjudication or None")
    reviewers = [submission.reviewer_id for submission in submissions]
    if len(set(reviewers)) != len(reviewers):
        raise ValueError("review submissions must use distinct reviewer ids")
    if any(submission.target_id != target.target_id for submission in submissions):
        raise ValueError("all review submissions must reference the target")

    value_sets = {_normalized_values_key(submission.accepted_normalized_values) for submission in submissions}
    source_keys = {_source_identity_key(submission.source) for submission in submissions}
    consensus = len(value_sets) == 1 and len(source_keys) == 1

    if adjudication is None:
        if not consensus:
            raise ValueError("review disagreement requires independent adjudication")
        accepted = _canonical_values(submissions[0].accepted_normalized_values)
        source = submissions[0].source
    else:
        if adjudication.target_id != target.target_id:
            raise ValueError("adjudication must reference the target")
        if adjudication.adjudicator_id in set(reviewers):
            raise ValueError("adjudicator must be independent of the original reviewers")
        accepted = _canonical_values(adjudication.accepted_normalized_values)
        source = adjudication.source

    return ExtractionReviewRecord(
        target=target,
        submissions=submissions,
        accepted_normalized_values=accepted,
        source=source,
        adjudication=adjudication,
    )


def _canonical_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _normalized_values_key(values: tuple[str, ...]) -> tuple[str, ...]:
    return _canonical_values(values)


def _source_identity_key(source: SourceLocation) -> tuple[object, ...]:
    return (
        source.artifact_id,
        source.page,
        source.section,
        source.table,
        source.figure,
        source.row,
        source.column,
    )


def _review_target_payload(target: ExtractionReviewTarget) -> dict[str, object]:
    payload = asdict(target)
    payload["kind"] = target.kind.value
    return payload


def _submission_payload(submission: ExtractionReviewSubmission) -> dict[str, object]:
    return {
        "target_id": submission.target_id,
        "reviewer_id": submission.reviewer_id,
        "accepted_normalized_values": sorted(submission.accepted_normalized_values),
        "source": asdict(submission.source),
        "note": submission.note,
    }


def _adjudication_payload(adjudication: ExtractionAdjudication) -> dict[str, object]:
    return {
        "target_id": adjudication.target_id,
        "adjudicator_id": adjudication.adjudicator_id,
        "accepted_normalized_values": sorted(adjudication.accepted_normalized_values),
        "source": asdict(adjudication.source),
        "note": adjudication.note,
    }


def _gold_target_payload(target: ExtractionGoldTarget) -> dict[str, object]:
    return {
        "target_id": target.target_id,
        "paper_id": target.paper_id,
        "article_family_id": target.article_family_id,
        "object_type": target.object_type,
        "key": target.key,
        "kind": target.kind.value,
        "accepted_normalized_values": sorted(target.accepted_normalized_values),
        "source": asdict(target.source),
        "critical_for_hard_audit": target.critical_for_hard_audit,
        "reviewers": sorted(target.reviewers),
        "adjudicated": target.adjudicated,
        "review_record_sha256": target.review_record_sha256,
    }


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_nonempty_string_tuple(value: object, *, label: str) -> None:
    if not isinstance(value, tuple) or not value:
        raise TypeError(f"{label} must be a non-empty tuple of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} must contain non-empty strings")


def _require_schema_version(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != 1:
        raise ValueError(f"{label} schema_version must be integer 1")
