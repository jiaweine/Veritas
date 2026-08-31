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
        required = (
            self.target_id,
            self.paper_id,
            self.article_family_id,
            self.object_type,
            self.key,
        )
        if any(not value.strip() for value in required):
            raise ValueError("review target identity fields cannot be empty")


@dataclass(frozen=True)
class ExtractionReviewSubmission:
    target_id: str
    reviewer_id: str
    accepted_normalized_values: tuple[str, ...]
    source: SourceLocation
    note: str = ""

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.reviewer_id.strip():
            raise ValueError("target_id and reviewer_id are required")
        if not self.accepted_normalized_values:
            raise ValueError("review submission requires at least one accepted normalized value")
        if any(not value.strip() for value in self.accepted_normalized_values):
            raise ValueError("accepted normalized values cannot be empty")


@dataclass(frozen=True)
class ExtractionAdjudication:
    target_id: str
    adjudicator_id: str
    accepted_normalized_values: tuple[str, ...]
    source: SourceLocation
    note: str

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.adjudicator_id.strip():
            raise ValueError("target_id and adjudicator_id are required")
        if not self.accepted_normalized_values:
            raise ValueError("adjudication requires at least one accepted normalized value")
        if not self.note.strip():
            raise ValueError("adjudication note is required")


@dataclass(frozen=True)
class ExtractionReviewRecord:
    target: ExtractionReviewTarget
    submissions: tuple[ExtractionReviewSubmission, ...]
    accepted_normalized_values: tuple[str, ...]
    source: SourceLocation
    adjudication: ExtractionAdjudication | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if len(self.submissions) < 2:
            raise ValueError("review record requires at least two independent submissions")
        reviewers = [submission.reviewer_id for submission in self.submissions]
        if len(set(reviewers)) != len(reviewers):
            raise ValueError("review submissions must use distinct reviewer ids")
        if any(submission.target_id != self.target.target_id for submission in self.submissions):
            raise ValueError("review submissions must reference the review target")
        if self.adjudication is not None:
            if self.adjudication.target_id != self.target.target_id:
                raise ValueError("adjudication must reference the review target")
            if self.adjudication.adjudicator_id in set(reviewers):
                raise ValueError("adjudicator must be independent of the original reviewers")
        if not self.accepted_normalized_values:
            raise ValueError("review record requires accepted normalized values")

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
        if not self.targets:
            raise ValueError("gold manifest requires at least one target")
        target_ids = [target.target_id for target in self.targets]
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("gold manifest target_id values must be unique")
        if not self.split_salt.strip() or not self.review_protocol_version.strip():
            raise ValueError("split_salt and review_protocol_version are required")
        if not _SHA256_RE.fullmatch(self.source_seed_manifest_sha256):
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


def resolve_extraction_reviews(
    target: ExtractionReviewTarget,
    submissions: tuple[ExtractionReviewSubmission, ...] | list[ExtractionReviewSubmission],
    *,
    adjudication: ExtractionAdjudication | None = None,
) -> ExtractionReviewRecord:
    submissions = tuple(submissions)
    if len(submissions) < 2:
        raise ValueError("at least two independent review submissions are required")
    reviewers = [submission.reviewer_id for submission in submissions]
    if len(set(reviewers)) != len(reviewers):
        raise ValueError("review submissions must use distinct reviewer ids")
    if any(submission.target_id != target.target_id for submission in submissions):
        raise ValueError("all review submissions must reference the target")

    value_sets = {_normalized_values_key(submission.accepted_normalized_values) for submission in submissions}
    source_keys = {_source_identity_key(submission.source) for submission in submissions}
    consensus = len(value_sets) == 1 and len(source_keys) == 1

    if consensus:
        accepted = _canonical_values(submissions[0].accepted_normalized_values)
        source = submissions[0].source
        if adjudication is not None:
            raise ValueError("adjudication is not needed when independent reviewers already agree")
    else:
        if adjudication is None:
            raise ValueError("review disagreement requires independent adjudication")
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
