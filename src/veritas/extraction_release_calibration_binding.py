from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .benchmark import BenchmarkSplit
from .extraction_calibration_archive import (
    ExtractionDevelopmentCalibrationFreeze,
    ExtractionPretestPilotThresholdPolicy,
    ExtractionTestEvaluationArchive,
)
from .extraction_evidence_workflow import ExtractionEvidencePlan, ExtractionSplitTargetManifest
from .extraction_execution_evidence import extraction_prediction_semantics_sha256
from .extraction_release_archive import (
    ExtractionReleaseEvidenceBundle,
    load_extraction_prediction_artifact,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BINDING_KEYS = frozenset(
    {
        "schema_version",
        "release_bundle_sha256",
        "release_bundle_file_sha256",
        "evidence_plan_sha256",
        "threshold_grid_sha256",
        "pilot_policy_file_sha256",
        "threshold_policy_sha256",
        "development_calibration_freeze_sha256",
        "development_calibration_freeze_file_sha256",
        "frozen_threshold_sha256",
        "selected_threshold_id",
        "selected_threshold",
        "development_manifest_sha256",
        "development_manifest_file_sha256",
        "test_evaluation_archive_sha256",
        "test_evaluation_archive_file_sha256",
        "test_evaluation_lock_sha256",
        "test_manifest_sha256",
        "test_manifest_file_sha256",
        "production_authorized",
    }
)


@dataclass(frozen=True)
class ExtractionReleaseCalibrationBinding:
    release_bundle_sha256: str
    release_bundle_file_sha256: str
    evidence_plan_sha256: str
    threshold_grid_sha256: str
    pilot_policy_file_sha256: str
    threshold_policy_sha256: str
    development_calibration_freeze_sha256: str
    development_calibration_freeze_file_sha256: str
    frozen_threshold_sha256: str
    selected_threshold_id: str
    selected_threshold: float
    development_manifest_sha256: str
    development_manifest_file_sha256: str
    test_evaluation_archive_sha256: str
    test_evaluation_archive_file_sha256: str
    test_evaluation_lock_sha256: str
    test_manifest_sha256: str
    test_manifest_file_sha256: str
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("release_bundle_sha256", self.release_bundle_sha256),
            ("release_bundle_file_sha256", self.release_bundle_file_sha256),
            ("evidence_plan_sha256", self.evidence_plan_sha256),
            ("threshold_grid_sha256", self.threshold_grid_sha256),
            ("pilot_policy_file_sha256", self.pilot_policy_file_sha256),
            ("threshold_policy_sha256", self.threshold_policy_sha256),
            (
                "development_calibration_freeze_sha256",
                self.development_calibration_freeze_sha256,
            ),
            (
                "development_calibration_freeze_file_sha256",
                self.development_calibration_freeze_file_sha256,
            ),
            ("frozen_threshold_sha256", self.frozen_threshold_sha256),
            ("development_manifest_sha256", self.development_manifest_sha256),
            (
                "development_manifest_file_sha256",
                self.development_manifest_file_sha256,
            ),
            ("test_evaluation_archive_sha256", self.test_evaluation_archive_sha256),
            (
                "test_evaluation_archive_file_sha256",
                self.test_evaluation_archive_file_sha256,
            ),
            ("test_evaluation_lock_sha256", self.test_evaluation_lock_sha256),
            ("test_manifest_sha256", self.test_manifest_sha256),
            ("test_manifest_file_sha256", self.test_manifest_file_sha256),
        ):
            _require_sha256(value, label=label)
        _require_nonempty_string(self.selected_threshold_id, label="selected_threshold_id")
        _require_finite_nonnegative_number(self.selected_threshold, label="selected_threshold")
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("release calibration bindings are non-production only")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("release calibration binding schema_version must be integer 1")
        if self.schema_version != 1:
            raise ValueError("release calibration binding schema_version must be integer 1")

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


def build_extraction_release_calibration_binding(
    *,
    bundle: ExtractionReleaseEvidenceBundle,
    bundle_path: str | Path,
    plan: ExtractionEvidencePlan,
    threshold_grid_sha256: str,
    pilot_policy: ExtractionPretestPilotThresholdPolicy,
    pilot_policy_path: str | Path,
    development_freeze: ExtractionDevelopmentCalibrationFreeze,
    development_freeze_path: str | Path,
    development_manifest: ExtractionSplitTargetManifest,
    development_manifest_path: str | Path,
    test_evaluation_archive: ExtractionTestEvaluationArchive,
    test_evaluation_archive_path: str | Path,
    test_manifest: ExtractionSplitTargetManifest,
    test_manifest_path: str | Path,
    release_artifact_root: str | Path,
) -> ExtractionReleaseCalibrationBinding:
    if not isinstance(bundle, ExtractionReleaseEvidenceBundle):
        raise TypeError("bundle must be an ExtractionReleaseEvidenceBundle")
    if not isinstance(plan, ExtractionEvidencePlan):
        raise TypeError("plan must be an ExtractionEvidencePlan")
    _require_sha256(threshold_grid_sha256, label="threshold_grid_sha256")
    if not isinstance(pilot_policy, ExtractionPretestPilotThresholdPolicy):
        raise TypeError("pilot_policy must be an ExtractionPretestPilotThresholdPolicy")
    if not isinstance(development_freeze, ExtractionDevelopmentCalibrationFreeze):
        raise TypeError("development_freeze must be an ExtractionDevelopmentCalibrationFreeze")
    if not isinstance(test_evaluation_archive, ExtractionTestEvaluationArchive):
        raise TypeError("test_evaluation_archive must be an ExtractionTestEvaluationArchive")

    if development_manifest.split is not BenchmarkSplit.DEVELOPMENT:
        raise ValueError("development manifest must use the DEVELOPMENT split")
    if test_manifest.split is not BenchmarkSplit.TEST:
        raise ValueError("test manifest must use the TEST split")
    if development_manifest.gold_manifest_sha256 != test_manifest.gold_manifest_sha256:
        raise ValueError("DEVELOPMENT and TEST manifests use different reviewed gold")
    if development_manifest.split_lock_sha256 != test_manifest.split_lock_sha256:
        raise ValueError("DEVELOPMENT and TEST manifests use different article-family split locks")
    if set(development_manifest.article_family_ids) & set(test_manifest.article_family_ids):
        raise ValueError("DEVELOPMENT and TEST article-family membership overlaps")
    if set(development_manifest.target_ids) & set(test_manifest.target_ids):
        raise ValueError("DEVELOPMENT and TEST target membership overlaps")

    if pilot_policy.bound_evidence_plan_sha256 != plan.sha256():
        raise ValueError("pilot threshold policy is bound to a different evidence plan")
    if float(pilot_policy.benchmark_confidence) != float(plan.benchmark_confidence):
        raise ValueError("pilot threshold policy benchmark confidence differs from evidence plan")
    if pilot_policy.source_file_sha256 != _file_sha256(pilot_policy_path):
        raise ValueError("pilot threshold policy exact bytes differ from loaded policy")
    if development_freeze.evidence_plan_sha256 != plan.sha256():
        raise ValueError("DEVELOPMENT freeze is bound to a different evidence plan")
    if float(development_freeze.benchmark_confidence) != float(plan.benchmark_confidence):
        raise ValueError("DEVELOPMENT freeze benchmark confidence differs from evidence plan")
    if development_freeze.pilot_policy_file_sha256 != pilot_policy.source_file_sha256:
        raise ValueError("DEVELOPMENT freeze is bound to different pilot-policy bytes")
    if development_freeze.threshold_policy != pilot_policy.threshold_policy:
        raise ValueError("DEVELOPMENT freeze threshold policy differs from pre-TEST pilot policy")
    if bundle.threshold_policy != development_freeze.threshold_policy:
        raise ValueError("release bundle threshold policy differs from DEVELOPMENT freeze")
    if development_manifest.sha256() != development_freeze.development_manifest_sha256:
        raise ValueError("DEVELOPMENT manifest differs from DEVELOPMENT freeze")

    freeze_file_sha256 = _file_sha256(development_freeze_path)
    if test_evaluation_archive.development_calibration_freeze_sha256 != development_freeze.sha256():
        raise ValueError("TEST evaluation archive is bound to a different DEVELOPMENT freeze")
    if (
        test_evaluation_archive.development_calibration_freeze_file_sha256
        != freeze_file_sha256
    ):
        raise ValueError("TEST evaluation archive is bound to different DEVELOPMENT freeze bytes")
    if test_evaluation_archive.frozen_threshold_sha256 != development_freeze.frozen_threshold.sha256():
        raise ValueError("TEST evaluation archive is bound to a different frozen threshold")
    if test_evaluation_archive.test_manifest_sha256 != test_manifest.sha256():
        raise ValueError("TEST evaluation archive is bound to a different TEST manifest")
    test_manifest_file_sha256 = _file_sha256(test_manifest_path)
    if test_evaluation_archive.test_manifest_file_sha256 != test_manifest_file_sha256:
        raise ValueError("TEST evaluation archive is bound to different TEST manifest bytes")

    _verify_bundle_threshold_grid(bundle, development_freeze)
    _verify_development_prediction_archives(
        bundle,
        development_freeze,
        release_artifact_root=release_artifact_root,
    )

    bundle_file_sha256 = _file_sha256(bundle_path)
    return ExtractionReleaseCalibrationBinding(
        release_bundle_sha256=bundle.sha256(),
        release_bundle_file_sha256=bundle_file_sha256,
        evidence_plan_sha256=plan.sha256(),
        threshold_grid_sha256=threshold_grid_sha256,
        pilot_policy_file_sha256=pilot_policy.source_file_sha256,
        threshold_policy_sha256=pilot_policy.threshold_policy.sha256(),
        development_calibration_freeze_sha256=development_freeze.sha256(),
        development_calibration_freeze_file_sha256=freeze_file_sha256,
        frozen_threshold_sha256=development_freeze.frozen_threshold.sha256(),
        selected_threshold_id=development_freeze.frozen_threshold.threshold_id,
        selected_threshold=development_freeze.frozen_threshold.threshold,
        development_manifest_sha256=development_manifest.sha256(),
        development_manifest_file_sha256=_file_sha256(development_manifest_path),
        test_evaluation_archive_sha256=test_evaluation_archive.sha256(),
        test_evaluation_archive_file_sha256=_file_sha256(test_evaluation_archive_path),
        test_evaluation_lock_sha256=test_evaluation_archive.test_evaluation_lock.sha256(),
        test_manifest_sha256=test_manifest.sha256(),
        test_manifest_file_sha256=test_manifest_file_sha256,
    )


def verify_extraction_release_calibration_binding(
    binding: ExtractionReleaseCalibrationBinding,
    *,
    bundle: ExtractionReleaseEvidenceBundle,
    bundle_path: str | Path,
    plan: ExtractionEvidencePlan,
    threshold_grid_sha256: str,
    pilot_policy: ExtractionPretestPilotThresholdPolicy,
    pilot_policy_path: str | Path,
    development_freeze: ExtractionDevelopmentCalibrationFreeze,
    development_freeze_path: str | Path,
    development_manifest: ExtractionSplitTargetManifest,
    development_manifest_path: str | Path,
    test_evaluation_archive: ExtractionTestEvaluationArchive,
    test_evaluation_archive_path: str | Path,
    test_manifest: ExtractionSplitTargetManifest,
    test_manifest_path: str | Path,
    release_artifact_root: str | Path,
) -> None:
    expected = build_extraction_release_calibration_binding(
        bundle=bundle,
        bundle_path=bundle_path,
        plan=plan,
        threshold_grid_sha256=threshold_grid_sha256,
        pilot_policy=pilot_policy,
        pilot_policy_path=pilot_policy_path,
        development_freeze=development_freeze,
        development_freeze_path=development_freeze_path,
        development_manifest=development_manifest,
        development_manifest_path=development_manifest_path,
        test_evaluation_archive=test_evaluation_archive,
        test_evaluation_archive_path=test_evaluation_archive_path,
        test_manifest=test_manifest,
        test_manifest_path=test_manifest_path,
        release_artifact_root=release_artifact_root,
    )
    if binding != expected:
        raise ValueError("release calibration binding differs from exact supplied release/freeze/TEST chain")


def extraction_release_calibration_binding_json_payload(
    binding: ExtractionReleaseCalibrationBinding,
) -> dict[str, object]:
    if not isinstance(binding, ExtractionReleaseCalibrationBinding):
        raise TypeError("binding must be an ExtractionReleaseCalibrationBinding")
    return asdict(binding)


def load_extraction_release_calibration_binding(
    path: str | Path,
) -> ExtractionReleaseCalibrationBinding:
    payload = _load_strict_json_file(path, label="release calibration binding")
    _require_exact_keys(payload, _BINDING_KEYS, label="release calibration binding")
    return ExtractionReleaseCalibrationBinding(**payload)


def _verify_bundle_threshold_grid(
    bundle: ExtractionReleaseEvidenceBundle,
    freeze: ExtractionDevelopmentCalibrationFreeze,
) -> None:
    expected = {item.threshold_id: float(item.threshold) for item in freeze.observations}
    for label, runs in (("DEVELOPMENT", bundle.development_runs), ("TEST", bundle.test_runs)):
        actual = {run.threshold_id: float(run.threshold) for run in runs}
        if actual != expected:
            raise ValueError(f"release bundle {label} threshold grid differs from DEVELOPMENT freeze")


def _verify_development_prediction_archives(
    bundle: ExtractionReleaseEvidenceBundle,
    freeze: ExtractionDevelopmentCalibrationFreeze,
    *,
    release_artifact_root: str | Path,
) -> None:
    root = Path(release_artifact_root).resolve(strict=True)
    archived = {item.threshold_id: item for item in freeze.observations}
    for run in bundle.development_runs:
        observation = archived[run.threshold_id]
        artifact_path = _resolve_regular_file(root, run.prediction_artifact_path)
        if _file_sha256(artifact_path) != observation.prediction_artifact_sha256:
            raise ValueError(
                "release DEVELOPMENT prediction bytes differ from DEVELOPMENT freeze: "
                f"{run.threshold_id!r}"
            )
        predictions = load_extraction_prediction_artifact(artifact_path)
        if extraction_prediction_semantics_sha256(predictions) != observation.prediction_semantics_sha256:
            raise ValueError(
                "release DEVELOPMENT prediction semantics differ from DEVELOPMENT freeze: "
                f"{run.threshold_id!r}"
            )


def _resolve_regular_file(root: Path, relative_path: str) -> Path:
    candidate = root / relative_path
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("release prediction artifact must be a regular non-symlink file")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("release prediction artifact escapes release-artifact root") from exc
    return resolved


def _file_sha256(path: str | Path) -> str:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"release binding input must be a regular non-symlink file: {source}")
    digest = sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_strict_json_file(path: str | Path, *, label: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc

    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"{label} contains unsupported JSON numeric constant: {value}")

    try:
        payload = json.loads(
            text,
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{label} root must be an object")
    return payload


def _require_exact_keys(value: object, expected: frozenset[str], *, label: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        unknown = tuple(sorted(actual - expected))
        raise ValueError(f"{label} keys differ from schema; missing={missing!r}, unknown={unknown!r}")


def _require_sha256(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_nonempty_string(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_finite_nonnegative_number(value: object, *, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{label} must be a finite non-negative number")


def _stable_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()
