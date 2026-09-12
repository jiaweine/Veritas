from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ._strict_json import load_strict_json_object, require_exact_object_keys
from .extraction_evidence_workflow import (
    ExtractionEvidencePlan,
    ExtractionThresholdGrid,
    extraction_evidence_plan_payload,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "plan",
        "threshold_grid",
        "plan_sha256",
        "production_authorized",
    }
)
_PLAN_KEYS = frozenset(
    {
        "sampling_frame_sha256",
        "sampling_frame_source_manifest_sha256",
        "source_seed_manifest_sha256",
        "seed_target_universe_sha256",
        "review_protocol_version",
        "split_salt",
        "threshold_grid_sha256",
        "train_fraction",
        "development_fraction",
        "benchmark_confidence",
        "schema_version",
    }
)
_THRESHOLD_POINT_KEYS = frozenset({"threshold_id", "threshold"})


def load_extraction_evidence_plan(
    path: str | Path,
) -> tuple[ExtractionEvidencePlan, ExtractionThresholdGrid]:
    payload = load_strict_json_object(path, label="extraction evidence plan")
    require_exact_object_keys(payload, _ROOT_KEYS, label="extraction evidence plan")
    _require_schema_version(payload["schema_version"], label="extraction evidence plan")
    _require_nonproduction(payload["production_authorized"])

    plan_payload = payload["plan"]
    require_exact_object_keys(
        plan_payload,
        _PLAN_KEYS,
        label="extraction evidence plan payload",
    )
    threshold_rows = payload["threshold_grid"]
    if not isinstance(threshold_rows, list) or not threshold_rows:
        raise ValueError("extraction evidence plan threshold_grid must be a non-empty array")
    for row in threshold_rows:
        require_exact_object_keys(
            row,
            _THRESHOLD_POINT_KEYS,
            label="extraction evidence plan threshold point",
        )

    threshold_grid = ExtractionThresholdGrid(
        points=tuple((row["threshold_id"], row["threshold"]) for row in threshold_rows)
    )
    plan = ExtractionEvidencePlan(
        sampling_frame_sha256=plan_payload["sampling_frame_sha256"],
        sampling_frame_source_manifest_sha256=plan_payload[
            "sampling_frame_source_manifest_sha256"
        ],
        source_seed_manifest_sha256=plan_payload["source_seed_manifest_sha256"],
        seed_target_universe_sha256=plan_payload["seed_target_universe_sha256"],
        review_protocol_version=plan_payload["review_protocol_version"],
        split_salt=plan_payload["split_salt"],
        threshold_grid_sha256=plan_payload["threshold_grid_sha256"],
        train_fraction=plan_payload["train_fraction"],
        development_fraction=plan_payload["development_fraction"],
        benchmark_confidence=plan_payload["benchmark_confidence"],
        schema_version=plan_payload["schema_version"],
    )

    archived_sha256 = payload["plan_sha256"]
    if not isinstance(archived_sha256, str) or not _SHA256_RE.fullmatch(archived_sha256):
        raise ValueError("extraction evidence plan plan_sha256 must be a lowercase SHA-256 digest")
    if plan.sha256() != archived_sha256:
        raise ValueError("extraction evidence plan payload does not match archived plan_sha256")
    if threshold_grid.sha256() != plan.threshold_grid_sha256:
        raise ValueError("extraction evidence plan threshold grid does not match plan commitment")
    return plan, threshold_grid


def extraction_evidence_plan_json_payload(
    plan: ExtractionEvidencePlan,
    threshold_grid: ExtractionThresholdGrid,
) -> dict[str, Any]:
    return extraction_evidence_plan_payload(plan, threshold_grid)


def _require_schema_version(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} schema_version must be integer 1")
    if value != 1:
        raise ValueError(f"{label} schema_version must be integer 1")


def _require_nonproduction(value: object) -> None:
    if type(value) is not bool:
        raise TypeError("extraction evidence plan production_authorized must be boolean")
    if value:
        raise ValueError("extraction evidence plans are non-production only")
