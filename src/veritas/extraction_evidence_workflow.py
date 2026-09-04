from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .benchmark import BenchmarkSplit
from .corpus import AccessTier, ArticleFamilySplitLock, CorpusPaper
from .extraction_benchmark import ExtractionSelectivityCurve
from .extraction_calibration import ExtractionTestEvaluationLock, FrozenExtractionThreshold
from .extraction_review import ExtractionGoldManifest
from .extraction_test_seal import ExtractionTestSetSeal

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAMPLING_FRAME_STATUS = "sampling_frame_only_unlabeled"


@dataclass(frozen=True)
class ExtractionSamplingFrame:
    papers: tuple[CorpusPaper, ...]
    source_manifest_sha256: str
    status: str = _SAMPLING_FRAME_STATUS
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.status != _SAMPLING_FRAME_STATUS:
            raise ValueError("extraction sampling frame must remain explicitly unlabeled")
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise ValueError("extraction sampling frame schema_version must be 1")
        _require_sha256(self.source_manifest_sha256, label="sampling-frame source manifest")
        if not self.papers:
            raise ValueError("extraction sampling frame requires at least one paper")
        paper_ids = [paper.paper_id for paper in self.papers]
        if len(set(paper_ids)) != len(paper_ids):
            raise ValueError("extraction sampling-frame paper ids must be unique")

    def paper_family_map(self) -> dict[str, str]:
        return {paper.paper_id: paper.article_family_id for paper in self.papers}

    def sha256(self) -> str:
        return _stable_sha256(
            {
                "schema_version": self.schema_version,
                "status": self.status,
                "source_manifest_sha256": self.source_manifest_sha256,
                "papers": [
                    _corpus_paper_payload(paper)
                    for paper in sorted(self.papers, key=lambda item: item.paper_id)
                ],
            }
        )


@dataclass(frozen=True)
class ExtractionThresholdGrid:
    points: tuple[tuple[str, float], ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise ValueError("threshold-grid schema_version must be 1")
        if not self.points:
            raise ValueError("threshold grid requires at least one point")
        ids = [threshold_id for threshold_id, _ in self.points]
        if len(set(ids)) != len(ids):
            raise ValueError("threshold-grid ids must be unique")
        if any(not isinstance(value, str) or not value.strip() for value in ids):
            raise ValueError("threshold-grid ids must be non-empty strings")
        thresholds = [threshold for _, threshold in self.points]
        if any(
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
            or float(threshold) < 0.0
            for threshold in thresholds
        ):
            raise ValueError("threshold-grid values must be finite non-negative numbers")
        if len({float(value) for value in thresholds}) != len(thresholds):
            raise ValueError("threshold-grid numeric values must be unique")

    @property
    def threshold_ids(self) -> tuple[str, ...]:
        return tuple(sorted(threshold_id for threshold_id, _ in self.points))

    @property
    def thresholds(self) -> tuple[float, ...]:
        return tuple(sorted(float(threshold) for _, threshold in self.points))

    def threshold_for_id(self, threshold_id: str) -> float:
        for candidate_id, threshold in self.points:
            if candidate_id == threshold_id:
                return float(threshold)
        raise KeyError(threshold_id)

    def sha256(self) -> str:
        return _stable_sha256(
            {
                "schema_version": self.schema_version,
                "points": [
                    {"threshold_id": threshold_id, "threshold": float(threshold)}
                    for threshold_id, threshold in sorted(self.points)
                ],
            }
        )


@dataclass(frozen=True)
class ExtractionEvidencePlan:
    sampling_frame_sha256: str
    sampling_frame_source_manifest_sha256: str
    source_seed_manifest_sha256: str
    review_protocol_version: str
    split_salt: str
    threshold_grid_sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("sampling_frame_sha256", self.sampling_frame_sha256),
            (
                "sampling_frame_source_manifest_sha256",
                self.sampling_frame_source_manifest_sha256,
            ),
            ("source_seed_manifest_sha256", self.source_seed_manifest_sha256),
            ("threshold_grid_sha256", self.threshold_grid_sha256),
        ):
            _require_sha256(value, label=label)
        if not isinstance(self.review_protocol_version, str) or not self.review_protocol_version.strip():
            raise ValueError("review_protocol_version is required")
        if not isinstance(self.split_salt, str) or not self.split_salt.strip():
            raise ValueError("split_salt is required")
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise ValueError("extraction evidence plan schema_version must be 1")

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class ExtractionEvidenceReleaseReceipt:
    plan_sha256: str
    gold_manifest_sha256: str
    split_lock_sha256: str
    frozen_threshold_sha256: str
    test_seal_sha256: str
    test_evaluation_lock_sha256: str
    development_curve_sha256: str
    test_curve_sha256: str
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("plan_sha256", self.plan_sha256),
            ("gold_manifest_sha256", self.gold_manifest_sha256),
            ("split_lock_sha256", self.split_lock_sha256),
            ("frozen_threshold_sha256", self.frozen_threshold_sha256),
            ("test_seal_sha256", self.test_seal_sha256),
            ("test_evaluation_lock_sha256", self.test_evaluation_lock_sha256),
            ("development_curve_sha256", self.development_curve_sha256),
            ("test_curve_sha256", self.test_curve_sha256),
        ):
            _require_sha256(value, label=label)
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("extraction evidence release receipts are non-production only")
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise ValueError("extraction evidence release receipt schema_version must be 1")

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


def file_sha256(path: str | Path) -> str:
    source_path = Path(path)
    if not source_path.is_file():
        raise ValueError("evidence-workflow manifest path must point to a file")
    return sha256(source_path.read_bytes()).hexdigest()


def load_extraction_sampling_frame(path: str | Path) -> ExtractionSamplingFrame:
    source_path = Path(path)
    raw = source_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("sampling-frame manifest must be UTF-8 JSON") from exc
    payload = _loads_strict_json(text)
    if not isinstance(payload, dict):
        raise TypeError("sampling-frame manifest root must be an object")
    if "labels" in payload:
        raise ValueError("sampling-frame manifest must not contain labels")
    if payload.get("schema_version") != 1 or isinstance(payload.get("schema_version"), bool):
        raise ValueError("sampling-frame manifest schema_version must be 1")
    if payload.get("status") != _SAMPLING_FRAME_STATUS:
        raise ValueError("sampling-frame manifest must be explicitly unlabeled")
    rows = payload.get("papers")
    if not isinstance(rows, list) or not rows:
        raise ValueError("sampling-frame manifest requires a non-empty papers array")
    return ExtractionSamplingFrame(
        papers=tuple(_paper_from_mapping(row) for row in rows),
        source_manifest_sha256=sha256(raw).hexdigest(),
    )


def build_extraction_evidence_plan(
    sampling_frame: ExtractionSamplingFrame,
    threshold_grid: ExtractionThresholdGrid,
    *,
    source_seed_manifest_sha256: str,
    review_protocol_version: str = "independent-double-review-v1",
    split_salt: str,
) -> ExtractionEvidencePlan:
    _require_sha256(source_seed_manifest_sha256, label="source_seed_manifest_sha256")
    return ExtractionEvidencePlan(
        sampling_frame_sha256=sampling_frame.sha256(),
        sampling_frame_source_manifest_sha256=sampling_frame.source_manifest_sha256,
        source_seed_manifest_sha256=source_seed_manifest_sha256,
        review_protocol_version=review_protocol_version,
        split_salt=split_salt,
        threshold_grid_sha256=threshold_grid.sha256(),
    )


def build_extraction_evidence_release_receipt(
    *,
    plan: ExtractionEvidencePlan,
    sampling_frame: ExtractionSamplingFrame,
    threshold_grid: ExtractionThresholdGrid,
    gold_manifest: ExtractionGoldManifest,
    split_lock: ArticleFamilySplitLock,
    frozen_threshold: FrozenExtractionThreshold,
    development_manifest_sha256: str,
    test_seal: ExtractionTestSetSeal,
    test_evaluation_lock: ExtractionTestEvaluationLock,
    test_manifest_sha256: str,
    development_curve: ExtractionSelectivityCurve,
    test_curve: ExtractionSelectivityCurve,
) -> ExtractionEvidenceReleaseReceipt:
    _require_sha256(development_manifest_sha256, label="development_manifest_sha256")
    _require_sha256(test_manifest_sha256, label="test_manifest_sha256")
    if sampling_frame.sha256() != plan.sampling_frame_sha256:
        raise ValueError("sampling frame does not match the precommitted evidence plan")
    if sampling_frame.source_manifest_sha256 != plan.sampling_frame_source_manifest_sha256:
        raise ValueError("sampling-frame source bytes do not match the precommitted evidence plan")
    if threshold_grid.sha256() != plan.threshold_grid_sha256:
        raise ValueError("threshold grid does not match the precommitted evidence plan")
    if gold_manifest.source_seed_manifest_sha256 != plan.source_seed_manifest_sha256:
        raise ValueError("gold seed manifest differs from the precommitted evidence plan")
    if gold_manifest.review_protocol_version != plan.review_protocol_version:
        raise ValueError("gold review protocol differs from the precommitted evidence plan")
    if gold_manifest.split_salt != plan.split_salt:
        raise ValueError("gold split salt differs from the precommitted evidence plan")

    family_by_paper = sampling_frame.paper_family_map()
    for target in gold_manifest.targets:
        expected_family = family_by_paper.get(target.paper_id)
        if expected_family is None:
            raise ValueError(
                "gold target paper is outside the precommitted sampling frame: "
                f"{target.paper_id!r}"
            )
        if expected_family != target.article_family_id:
            raise ValueError(f"gold target article-family identity drifted: {target.target_id!r}")

    expected_split_lock = gold_manifest.build_split_lock(
        train_fraction=split_lock.train_fraction,
        development_fraction=split_lock.development_fraction,
    )
    if expected_split_lock.sha256() != split_lock.sha256():
        raise ValueError("split lock is not the deterministic lock for the reviewed gold manifest")
    if split_lock.split_salt != plan.split_salt:
        raise ValueError("split lock salt differs from the precommitted evidence plan")
    split_values = {split for _, split in split_lock.assignments}
    if BenchmarkSplit.DEVELOPMENT not in split_values:
        raise ValueError("release workflow requires at least one DEVELOPMENT article family")
    if BenchmarkSplit.TEST not in split_values:
        raise ValueError("release workflow requires at least one TEST article family")

    if tuple(sorted(frozen_threshold.candidate_threshold_ids)) != threshold_grid.threshold_ids:
        raise ValueError("frozen threshold candidate ids differ from the precommitted threshold grid")
    try:
        selected_threshold = threshold_grid.threshold_for_id(frozen_threshold.threshold_id)
    except KeyError as exc:
        raise ValueError("selected threshold id is not in the precommitted threshold grid") from exc
    if selected_threshold != frozen_threshold.threshold:
        raise ValueError("selected threshold value differs from the precommitted threshold grid")
    if frozen_threshold.development_manifest_sha256 != development_manifest_sha256:
        raise ValueError("frozen threshold is bound to a different DEVELOPMENT manifest")

    test_seal.validate(gold_manifest, split_lock)
    if test_evaluation_lock.frozen_threshold_sha256 != frozen_threshold.sha256():
        raise ValueError("TEST evaluation lock is not bound to the frozen DEVELOPMENT threshold")
    if test_evaluation_lock.test_manifest_sha256 != test_manifest_sha256:
        raise ValueError("TEST evaluation lock is bound to a different TEST manifest")

    expected_thresholds = threshold_grid.thresholds
    _require_curve_thresholds(development_curve, expected_thresholds, label="DEVELOPMENT")
    _require_curve_thresholds(test_curve, expected_thresholds, label="TEST")
    return ExtractionEvidenceReleaseReceipt(
        plan_sha256=plan.sha256(),
        gold_manifest_sha256=gold_manifest.sha256(),
        split_lock_sha256=split_lock.sha256(),
        frozen_threshold_sha256=frozen_threshold.sha256(),
        test_seal_sha256=test_seal.sha256(),
        test_evaluation_lock_sha256=test_evaluation_lock.sha256(),
        development_curve_sha256=_curve_sha256(development_curve),
        test_curve_sha256=_curve_sha256(test_curve),
    )


def extraction_evidence_plan_payload(
    plan: ExtractionEvidencePlan,
    threshold_grid: ExtractionThresholdGrid,
) -> dict[str, Any]:
    if threshold_grid.sha256() != plan.threshold_grid_sha256:
        raise ValueError("threshold grid does not match extraction evidence plan")
    return {
        "schema_version": 1,
        "plan": asdict(plan),
        "threshold_grid": [
            {"threshold_id": threshold_id, "threshold": float(threshold)}
            for threshold_id, threshold in sorted(threshold_grid.points)
        ],
        "plan_sha256": plan.sha256(),
        "production_authorized": False,
    }


def _require_curve_thresholds(
    curve: ExtractionSelectivityCurve,
    expected: tuple[float, ...],
    *,
    label: str,
) -> None:
    actual = tuple(float(point.threshold) for point in curve.points)
    if actual != expected:
        raise ValueError(
            f"{label} selectivity curve does not match the precommitted threshold grid"
        )


def _curve_sha256(curve: ExtractionSelectivityCurve) -> str:
    return _stable_sha256(
        {
            "points": [asdict(point) for point in curve.points],
            "production_authorized": False,
        }
    )


def _paper_from_mapping(value: object) -> CorpusPaper:
    if not isinstance(value, dict):
        raise TypeError("sampling-frame paper rows must be objects")
    required = (
        "paper_id",
        "article_family_id",
        "title",
        "discipline",
        "year",
        "source_url",
        "access_tier",
    )
    if any(key not in value for key in required):
        raise ValueError("sampling-frame paper row is missing required identity metadata")
    year = value["year"]
    if isinstance(year, bool) or not isinstance(year, int):
        raise TypeError("sampling-frame paper year must be an integer")
    redistributable = value.get("redistributable_artifacts", False)
    if type(redistributable) is not bool:
        raise TypeError("redistributable_artifacts must be a boolean")
    artifact_urls = value.get("artifact_urls", [])
    if not isinstance(artifact_urls, list) or any(not isinstance(item, str) for item in artifact_urls):
        raise TypeError("artifact_urls must be an array of strings")
    return CorpusPaper(
        paper_id=_required_string(value["paper_id"], label="paper_id"),
        article_family_id=_required_string(value["article_family_id"], label="article_family_id"),
        doi=_optional_string(value.get("doi"), label="doi"),
        title=_required_string(value["title"], label="title"),
        discipline=_required_string(value["discipline"], label="discipline"),
        year=year,
        source_url=_required_string(value["source_url"], label="source_url"),
        access_tier=AccessTier(value["access_tier"]),
        artifact_urls=tuple(artifact_urls),
        license_note=_optional_string(value.get("license_note"), label="license_note"),
        redistributable_artifacts=redistributable,
    )


def _corpus_paper_payload(paper: CorpusPaper) -> dict[str, Any]:
    return {
        "paper_id": paper.paper_id,
        "article_family_id": paper.article_family_id,
        "doi": paper.doi,
        "title": paper.title,
        "discipline": paper.discipline,
        "year": paper.year,
        "source_url": paper.source_url,
        "access_tier": paper.access_tier.value,
        "artifact_urls": list(paper.artifact_urls),
        "license_note": paper.license_note,
        "redistributable_artifacts": paper.redistributable_artifacts,
        "artifact_sha256": paper.artifact_sha256,
    }


def _loads_strict_json(text: str) -> Any:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"unsupported JSON numeric constant: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("sampling-frame manifest must be valid JSON") from exc


def _required_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"sampling-frame {label} must be a non-empty string")
    return value


def _optional_string(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"sampling-frame {label} must be a string or null")
    return value


def _require_sha256(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")


def _stable_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()
