from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256

from .benchmark import BenchmarkSplit


class AccessTier(str, Enum):
    PAPER_ONLY = "paper_only"
    PUBLIC_CODE_RESTRICTED_DATA = "public_code_restricted_data"
    PUBLIC_REPLICATION = "public_replication"
    PUBLIC_DATA_AND_CODE = "public_data_and_code"


class GroundTruthBasis(str, Enum):
    CONTROLLED_CORRUPTION = "controlled_corruption"
    MANUAL_RECONSTRUCTION = "manual_reconstruction"
    DOCUMENTED_REPRODUCTION = "documented_reproduction"


class ClaimExpectation(str, Enum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    UNVERIFIABLE = "unverifiable"
    NOT_RELEVANT = "not_relevant"


@dataclass(frozen=True)
class CorpusPaper:
    paper_id: str
    article_family_id: str
    doi: str | None
    title: str
    discipline: str
    year: int
    source_url: str
    access_tier: AccessTier
    artifact_urls: tuple[str, ...] = ()
    license_note: str | None = None
    redistributable_artifacts: bool = False
    artifact_sha256: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.paper_id.strip() or not self.article_family_id.strip():
            raise ValueError("paper_id and article_family_id are required")
        if self.year < 1900 or self.year > 2100:
            raise ValueError("year is outside the supported benchmark range")
        if not self.source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be an HTTP(S) URL")


@dataclass(frozen=True)
class ClaimGroundTruth:
    label_id: str
    paper_id: str
    object_id: str
    detector_id: str
    expectation: ClaimExpectation
    applicable: bool
    basis: GroundTruthBasis
    evidence_note: str
    evidence_urls: tuple[str, ...] = ()
    reviewers: tuple[str, ...] = ()
    adjudicated: bool = False
    corruption_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.basis is GroundTruthBasis.CONTROLLED_CORRUPTION and not self.corruption_manifest_sha256:
            raise ValueError("controlled corruptions require corruption_manifest_sha256")
        if (
            self.basis is not GroundTruthBasis.CONTROLLED_CORRUPTION
            and self.expectation in {ClaimExpectation.CONSISTENT, ClaimExpectation.INCONSISTENT}
            and (len(set(self.reviewers)) < 2 or not self.adjudicated)
        ):
            raise ValueError(
                "natural consistent/inconsistent labels require two independent reviewers and adjudication"
            )


@dataclass(frozen=True)
class ArticleFamilySplitLock:
    """Immutable benchmark split artifact keyed by article family rather than document version.

    Preprints, journal articles, corrections, and supplementary versions that share an
    ``article_family_id`` must remain in one split. The lock records the exact family universe,
    split fractions, salt, and resulting assignments so later corpus growth cannot silently move
    or replace held-out families.
    """

    split_salt: str
    train_fraction: float
    development_fraction: float
    assignments: tuple[tuple[str, BenchmarkSplit], ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_split_fractions(self.train_fraction, self.development_fraction)
        if not self.split_salt:
            raise ValueError("split_salt is required")
        family_ids = [family_id for family_id, _ in self.assignments]
        if len(set(family_ids)) != len(family_ids):
            raise ValueError("split lock article_family_id values must be unique")
        if any(not family_id.strip() for family_id in family_ids):
            raise ValueError("split lock article_family_id values cannot be empty")

    def split_for_family(self, article_family_id: str) -> BenchmarkSplit:
        for family_id, split in self.assignments:
            if family_id == article_family_id:
                return split
        raise KeyError(article_family_id)

    def validate_manifest(self, manifest: CorpusManifest) -> None:
        if manifest.split_salt != self.split_salt:
            raise ValueError("manifest split_salt does not match split lock")
        manifest_families = {paper.article_family_id for paper in manifest.papers}
        locked_families = {family_id for family_id, _ in self.assignments}
        if manifest_families != locked_families:
            missing = tuple(sorted(locked_families - manifest_families))
            added = tuple(sorted(manifest_families - locked_families))
            raise ValueError(
                "manifest article-family universe differs from split lock: "
                f"missing={missing!r}, added={added!r}"
            )
        for family_id, locked_split in self.assignments:
            expected = assign_article_family_split(
                family_id,
                salt=self.split_salt,
                train_fraction=self.train_fraction,
                development_fraction=self.development_fraction,
            )
            if expected is not locked_split:
                raise ValueError(f"split lock assignment does not match deterministic policy: {family_id}")

    def sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "split_salt": self.split_salt,
            "train_fraction": self.train_fraction,
            "development_fraction": self.development_fraction,
            "assignments": [
                {"article_family_id": family_id, "split": split.value}
                for family_id, split in sorted(self.assignments, key=lambda item: item[0])
            ],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()


@dataclass(frozen=True)
class CorpusManifest:
    papers: tuple[CorpusPaper, ...]
    labels: tuple[ClaimGroundTruth, ...]
    split_salt: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        paper_ids = {paper.paper_id for paper in self.papers}
        if len(paper_ids) != len(self.papers):
            raise ValueError("paper_id values must be unique")
        label_ids = {label.label_id for label in self.labels}
        if len(label_ids) != len(self.labels):
            raise ValueError("label_id values must be unique")
        missing = sorted({label.paper_id for label in self.labels} - paper_ids)
        if missing:
            raise ValueError(f"claim labels reference missing papers: {missing}")
        if not self.split_salt:
            raise ValueError("split_salt is required")

    def split_for_paper(self, paper_id: str) -> BenchmarkSplit:
        paper = next((paper for paper in self.papers if paper.paper_id == paper_id), None)
        if paper is None:
            raise KeyError(paper_id)
        return assign_article_family_split(paper.article_family_id, salt=self.split_salt)

    def build_split_lock(
        self,
        *,
        train_fraction: float = 0.60,
        development_fraction: float = 0.20,
    ) -> ArticleFamilySplitLock:
        _validate_split_fractions(train_fraction, development_fraction)
        families = sorted({paper.article_family_id for paper in self.papers})
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
            for family_id in families
        )
        return ArticleFamilySplitLock(
            split_salt=self.split_salt,
            train_fraction=train_fraction,
            development_fraction=development_fraction,
            assignments=assignments,
        )

    def sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "split_salt": self.split_salt,
            "papers": [
                _paper_payload(paper)
                for paper in sorted(self.papers, key=lambda item: item.paper_id)
            ],
            "labels": [
                _label_payload(label)
                for label in sorted(self.labels, key=lambda item: item.label_id)
            ],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()


def assign_article_family_split(
    article_family_id: str,
    *,
    salt: str,
    train_fraction: float = 0.60,
    development_fraction: float = 0.20,
) -> BenchmarkSplit:
    """Split by article family so preprint/journal/correction versions cannot leak across splits."""
    _validate_split_fractions(train_fraction, development_fraction)
    digest = sha256(f"{salt}:{article_family_id}".encode()).digest()
    value = int.from_bytes(digest[:8], "big") / float(2**64)
    if value < train_fraction:
        return BenchmarkSplit.TRAIN
    if value < train_fraction + development_fraction:
        return BenchmarkSplit.DEVELOPMENT
    return BenchmarkSplit.TEST


def _validate_split_fractions(train_fraction: float, development_fraction: float) -> None:
    if train_fraction <= 0 or development_fraction <= 0 or train_fraction + development_fraction >= 1:
        raise ValueError("split fractions must leave positive mass for the test split")


def _paper_payload(paper: CorpusPaper) -> dict[str, object]:
    payload = asdict(paper)
    payload["access_tier"] = paper.access_tier.value
    return payload


def _label_payload(label: ClaimGroundTruth) -> dict[str, object]:
    payload = asdict(label)
    payload["expectation"] = label.expectation.value
    payload["basis"] = label.basis.value
    return payload
