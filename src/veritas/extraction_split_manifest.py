from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from .benchmark import BenchmarkSplit
from .corpus import ArticleFamilySplitLock
from .extraction_benchmark import ExtractionBenchmarkReport, ExtractionGoldTarget
from .extraction_review import ExtractionGoldManifest


@dataclass(frozen=True)
class ExtractionSplitManifest:
    """Canonical split-specific target universe derived from reviewed gold and its split lock."""

    gold_manifest: ExtractionGoldManifest
    split_lock: ArticleFamilySplitLock
    split: BenchmarkSplit
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise ValueError("extraction split manifest schema_version must be 1")
        if not isinstance(self.split, BenchmarkSplit):
            raise TypeError("extraction split manifest split must be a BenchmarkSplit")
        if self.split_lock.manifest_sha256 != self.gold_manifest.sha256():
            raise ValueError("extraction split manifest lock is not bound to the supplied gold manifest")
        if self.split_lock.split_salt != self.gold_manifest.split_salt:
            raise ValueError("extraction split manifest lock salt differs from reviewed gold")
        expected_lock = self.gold_manifest.build_split_lock(
            train_fraction=self.split_lock.train_fraction,
            development_fraction=self.split_lock.development_fraction,
        )
        if expected_lock.sha256() != self.split_lock.sha256():
            raise ValueError("extraction split manifest requires the deterministic reviewed-gold split lock")
        if not self.targets:
            raise ValueError(f"extraction {self.split.value} split manifest has no targets")

    @property
    def targets(self) -> tuple[ExtractionGoldTarget, ...]:
        return tuple(
            sorted(
                (
                    target
                    for target in self.gold_manifest.targets
                    if self.split_lock.split_for_family(target.article_family_id) is self.split
                ),
                key=lambda target: target.target_id,
            )
        )

    @property
    def target_ids(self) -> tuple[str, ...]:
        return tuple(target.target_id for target in self.targets)

    @property
    def article_family_ids(self) -> tuple[str, ...]:
        return tuple(sorted({target.article_family_id for target in self.targets}))

    def sha256(self) -> str:
        raw = json.dumps(
            {
                "schema_version": self.schema_version,
                "gold_manifest_sha256": self.gold_manifest.sha256(),
                "split_lock_sha256": self.split_lock.sha256(),
                "split": self.split.value,
                "target_ids": list(self.target_ids),
                "article_family_ids": list(self.article_family_ids),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(raw).hexdigest()

    def validate_report_membership(self, report: ExtractionBenchmarkReport) -> None:
        if report.targets != len(self.targets):
            raise ValueError(
                f"{self.split.value} benchmark report target count differs from split manifest"
            )
        outcomes = tuple(report.outcomes)
        if len(outcomes) != len(self.targets):
            raise ValueError(
                f"{self.split.value} benchmark report must retain one outcome per split target"
            )
        outcome_ids = [outcome.target_id for outcome in outcomes]
        if len(set(outcome_ids)) != len(outcome_ids):
            raise ValueError(f"{self.split.value} benchmark report outcome target ids must be unique")
        if tuple(sorted(outcome_ids)) != self.target_ids:
            raise ValueError(
                f"{self.split.value} benchmark report target membership differs from split manifest"
            )
        target_by_id = {target.target_id: target for target in self.targets}
        for outcome in outcomes:
            target = target_by_id[outcome.target_id]
            expected_identity = (
                target.paper_id,
                target.article_family_id,
                target.kind,
                target.critical_for_hard_audit,
            )
            actual_identity = (
                outcome.paper_id,
                outcome.article_family_id,
                outcome.kind,
                outcome.critical_for_hard_audit,
            )
            if actual_identity != expected_identity:
                raise ValueError(
                    f"{self.split.value} benchmark report target identity drifted: "
                    f"{outcome.target_id!r}"
                )
