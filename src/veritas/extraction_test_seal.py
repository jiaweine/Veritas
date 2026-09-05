from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256

from .benchmark import BenchmarkSplit
from .corpus import ArticleFamilySplitLock
from .extraction_review import ExtractionGoldManifest

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExtractionTestSetSeal:
    gold_manifest_sha256: str
    split_lock_sha256: str
    test_article_family_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version != 1:
            raise ValueError("TEST seal schema_version must be integer 1")
        if not isinstance(self.gold_manifest_sha256, str) or not _SHA256_RE.fullmatch(
            self.gold_manifest_sha256
        ):
            raise ValueError("gold_manifest_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.split_lock_sha256, str) or not _SHA256_RE.fullmatch(
            self.split_lock_sha256
        ):
            raise ValueError("split_lock_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.test_article_family_ids, tuple) or not self.test_article_family_ids:
            raise ValueError("TEST seal requires a non-empty tuple of article families")
        if any(
            not isinstance(family_id, str) or not family_id.strip()
            for family_id in self.test_article_family_ids
        ):
            raise ValueError("test_article_family_ids must contain non-empty strings")
        if tuple(sorted(set(self.test_article_family_ids))) != self.test_article_family_ids:
            raise ValueError("test_article_family_ids must be unique and sorted")

    def sha256(self) -> str:
        raw = json.dumps(
            {
                "schema_version": self.schema_version,
                "gold_manifest_sha256": self.gold_manifest_sha256,
                "split_lock_sha256": self.split_lock_sha256,
                "test_article_family_ids": list(self.test_article_family_ids),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(raw).hexdigest()

    def validate(
        self,
        gold_manifest: ExtractionGoldManifest,
        split_lock: ArticleFamilySplitLock,
    ) -> None:
        if gold_manifest.sha256() != self.gold_manifest_sha256:
            raise ValueError("gold manifest SHA-256 does not match TEST seal")
        if split_lock.sha256() != self.split_lock_sha256:
            raise ValueError("split lock SHA-256 does not match TEST seal")
        if split_lock.manifest_sha256 != gold_manifest.sha256():
            raise ValueError("split lock is not bound to the supplied extraction gold manifest")
        expected = tuple(
            sorted(
                family_id
                for family_id, split in split_lock.assignments
                if split is BenchmarkSplit.TEST
            )
        )
        if expected != self.test_article_family_ids:
            raise ValueError("TEST family membership differs from sealed membership")


def seal_extraction_test_set(
    gold_manifest: ExtractionGoldManifest,
    split_lock: ArticleFamilySplitLock,
) -> ExtractionTestSetSeal:
    if not isinstance(gold_manifest, ExtractionGoldManifest):
        raise TypeError("gold_manifest must be an ExtractionGoldManifest")
    if not isinstance(split_lock, ArticleFamilySplitLock):
        raise TypeError("split_lock must be an ArticleFamilySplitLock")
    if split_lock.manifest_sha256 != gold_manifest.sha256():
        raise ValueError("split lock must be bound to the exact extraction gold manifest")
    test_families = tuple(
        sorted(
            family_id
            for family_id, split in split_lock.assignments
            if split is BenchmarkSplit.TEST
        )
    )
    if not test_families:
        raise ValueError("cannot seal an extraction TEST set with no TEST article families")
    return ExtractionTestSetSeal(
        gold_manifest_sha256=gold_manifest.sha256(),
        split_lock_sha256=split_lock.sha256(),
        test_article_family_ids=test_families,
    )
