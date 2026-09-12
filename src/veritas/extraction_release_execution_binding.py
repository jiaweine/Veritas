from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from .benchmark import BenchmarkSplit
from .extraction_evidence_workflow import ExtractionSplitTargetManifest
from .extraction_execution_evidence import (
    ExtractionExecutionAttestation,
    ExtractionExecutionPlan,
    extraction_prediction_semantics_sha256,
)
from .extraction_execution_evidence_json import load_extraction_execution_attestation
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
        "execution_plan_sha256",
        "execution_plan_file_sha256",
        "development_attestations",
        "test_attestations",
        "production_authorized",
    }
)
_ATTESTATION_KEYS = frozenset(
    {
        "threshold_id",
        "execution_id",
        "attestation_sha256",
        "attestation_file_sha256",
        "prediction_artifact_sha256",
        "prediction_semantics_sha256",
    }
)


@dataclass(frozen=True)
class ExtractionReleaseExecutionAttestationBinding:
    threshold_id: str
    execution_id: str
    attestation_sha256: str
    attestation_file_sha256: str
    prediction_artifact_sha256: str
    prediction_semantics_sha256: str

    def __post_init__(self) -> None:
        _require_nonempty_string(self.threshold_id, label="threshold_id")
        _require_nonempty_string(self.execution_id, label="execution_id")
        for label, value in (
            ("attestation_sha256", self.attestation_sha256),
            ("attestation_file_sha256", self.attestation_file_sha256),
            ("prediction_artifact_sha256", self.prediction_artifact_sha256),
            ("prediction_semantics_sha256", self.prediction_semantics_sha256),
        ):
            _require_sha256(value, label=label)


@dataclass(frozen=True)
class ExtractionReleaseExecutionBinding:
    release_bundle_sha256: str
    release_bundle_file_sha256: str
    execution_plan_sha256: str
    execution_plan_file_sha256: str
    development_attestations: tuple[ExtractionReleaseExecutionAttestationBinding, ...]
    test_attestations: tuple[ExtractionReleaseExecutionAttestationBinding, ...]
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for label, value in (
            ("release_bundle_sha256", self.release_bundle_sha256),
            ("release_bundle_file_sha256", self.release_bundle_file_sha256),
            ("execution_plan_sha256", self.execution_plan_sha256),
            ("execution_plan_file_sha256", self.execution_plan_file_sha256),
        ):
            _require_sha256(value, label=label)
        for label, items in (
            ("DEVELOPMENT", self.development_attestations),
            ("TEST", self.test_attestations),
        ):
            if not isinstance(items, tuple) or not items:
                raise ValueError(f"release execution binding requires {label} attestations")
            if any(
                not isinstance(item, ExtractionReleaseExecutionAttestationBinding)
                for item in items
            ):
                raise TypeError(f"release execution binding {label} attestations are invalid")
            threshold_ids = tuple(item.threshold_id for item in items)
            if threshold_ids != tuple(sorted(set(threshold_ids))):
                raise ValueError(
                    f"release execution binding {label} threshold ids must be unique and sorted"
                )
            execution_ids = tuple(item.execution_id for item in items)
            if len(set(execution_ids)) != len(execution_ids):
                raise ValueError(
                    f"release execution binding {label} execution ids must be unique"
                )
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("release execution bindings are non-production only")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("release execution binding schema_version must be integer 1")
        if self.schema_version != 1:
            raise ValueError("release execution binding schema_version must be integer 1")

    def sha256(self) -> str:
        return _stable_sha256(extraction_release_execution_binding_json_payload(self))


def build_extraction_release_execution_binding(
    *,
    bundle: ExtractionReleaseEvidenceBundle,
    bundle_path: str | Path,
    execution_plan: ExtractionExecutionPlan,
    execution_plan_path: str | Path,
    development_manifest: ExtractionSplitTargetManifest,
    test_manifest: ExtractionSplitTargetManifest,
    release_artifact_root: str | Path,
    development_attestation_paths: Mapping[str, str | Path],
    test_attestation_paths: Mapping[str, str | Path],
) -> ExtractionReleaseExecutionBinding:
    if not isinstance(bundle, ExtractionReleaseEvidenceBundle):
        raise TypeError("bundle must be an ExtractionReleaseEvidenceBundle")
    if not isinstance(execution_plan, ExtractionExecutionPlan):
        raise TypeError("execution_plan must be an ExtractionExecutionPlan")
    if development_manifest.split is not BenchmarkSplit.DEVELOPMENT:
        raise ValueError("development manifest must use the DEVELOPMENT split")
    if test_manifest.split is not BenchmarkSplit.TEST:
        raise ValueError("test manifest must use the TEST split")

    development = _verify_attestation_set(
        bundle.development_runs,
        split=BenchmarkSplit.DEVELOPMENT,
        target_manifest=development_manifest,
        execution_plan=execution_plan,
        release_artifact_root=release_artifact_root,
        attestation_paths=development_attestation_paths,
        label="DEVELOPMENT",
    )
    test = _verify_attestation_set(
        bundle.test_runs,
        split=BenchmarkSplit.TEST,
        target_manifest=test_manifest,
        execution_plan=execution_plan,
        release_artifact_root=release_artifact_root,
        attestation_paths=test_attestation_paths,
        label="TEST",
    )
    return ExtractionReleaseExecutionBinding(
        release_bundle_sha256=bundle.sha256(),
        release_bundle_file_sha256=_file_sha256(bundle_path),
        execution_plan_sha256=execution_plan.sha256(),
        execution_plan_file_sha256=_file_sha256(execution_plan_path),
        development_attestations=development,
        test_attestations=test,
    )


def verify_extraction_release_execution_binding(
    binding: ExtractionReleaseExecutionBinding,
    *,
    bundle: ExtractionReleaseEvidenceBundle,
    bundle_path: str | Path,
    execution_plan: ExtractionExecutionPlan,
    execution_plan_path: str | Path,
    development_manifest: ExtractionSplitTargetManifest,
    test_manifest: ExtractionSplitTargetManifest,
    release_artifact_root: str | Path,
    development_attestation_paths: Mapping[str, str | Path],
    test_attestation_paths: Mapping[str, str | Path],
) -> None:
    expected = build_extraction_release_execution_binding(
        bundle=bundle,
        bundle_path=bundle_path,
        execution_plan=execution_plan,
        execution_plan_path=execution_plan_path,
        development_manifest=development_manifest,
        test_manifest=test_manifest,
        release_artifact_root=release_artifact_root,
        development_attestation_paths=development_attestation_paths,
        test_attestation_paths=test_attestation_paths,
    )
    if binding != expected:
        raise ValueError(
            "release execution binding differs from exact supplied release/attestation chain"
        )


def extraction_release_execution_binding_json_payload(
    binding: ExtractionReleaseExecutionBinding,
) -> dict[str, object]:
    if not isinstance(binding, ExtractionReleaseExecutionBinding):
        raise TypeError("binding must be an ExtractionReleaseExecutionBinding")
    return {
        "schema_version": binding.schema_version,
        "release_bundle_sha256": binding.release_bundle_sha256,
        "release_bundle_file_sha256": binding.release_bundle_file_sha256,
        "execution_plan_sha256": binding.execution_plan_sha256,
        "execution_plan_file_sha256": binding.execution_plan_file_sha256,
        "development_attestations": [asdict(item) for item in binding.development_attestations],
        "test_attestations": [asdict(item) for item in binding.test_attestations],
        "production_authorized": binding.production_authorized,
    }


def load_extraction_release_execution_binding(
    path: str | Path,
) -> ExtractionReleaseExecutionBinding:
    payload = _load_strict_json_file(path, label="release execution binding")
    _require_exact_keys(payload, _BINDING_KEYS, label="release execution binding")
    return ExtractionReleaseExecutionBinding(
        release_bundle_sha256=payload["release_bundle_sha256"],
        release_bundle_file_sha256=payload["release_bundle_file_sha256"],
        execution_plan_sha256=payload["execution_plan_sha256"],
        execution_plan_file_sha256=payload["execution_plan_file_sha256"],
        development_attestations=_attestation_rows(
            payload["development_attestations"], label="DEVELOPMENT"
        ),
        test_attestations=_attestation_rows(payload["test_attestations"], label="TEST"),
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def _verify_attestation_set(
    runs,
    *,
    split: BenchmarkSplit,
    target_manifest: ExtractionSplitTargetManifest,
    execution_plan: ExtractionExecutionPlan,
    release_artifact_root: str | Path,
    attestation_paths: Mapping[str, str | Path],
    label: str,
) -> tuple[ExtractionReleaseExecutionAttestationBinding, ...]:
    run_by_threshold = {run.threshold_id: run for run in runs}
    if len(run_by_threshold) != len(runs):
        raise ValueError(f"release {label} threshold ids must be unique")
    if set(attestation_paths) != set(run_by_threshold):
        raise ValueError(f"release {label} attestation membership differs from bundle runs")

    root = Path(release_artifact_root).resolve(strict=True)
    result: list[ExtractionReleaseExecutionAttestationBinding] = []
    for threshold_id in sorted(run_by_threshold):
        run = run_by_threshold[threshold_id]
        path = Path(attestation_paths[threshold_id])
        attestation = load_extraction_execution_attestation(path)
        _verify_attestation(
            attestation,
            run=run,
            split=split,
            target_manifest=target_manifest,
            execution_plan=execution_plan,
            release_artifact_root=root,
            label=label,
        )
        result.append(
            ExtractionReleaseExecutionAttestationBinding(
                threshold_id=threshold_id,
                execution_id=attestation.execution_id,
                attestation_sha256=attestation.sha256(),
                attestation_file_sha256=_file_sha256(path),
                prediction_artifact_sha256=attestation.prediction_artifact_sha256,
                prediction_semantics_sha256=attestation.prediction_semantics_sha256,
            )
        )
    return tuple(result)


def _verify_attestation(
    attestation: ExtractionExecutionAttestation,
    *,
    run,
    split: BenchmarkSplit,
    target_manifest: ExtractionSplitTargetManifest,
    execution_plan: ExtractionExecutionPlan,
    release_artifact_root: Path,
    label: str,
) -> None:
    if attestation.execution_plan_sha256 != execution_plan.sha256():
        raise ValueError(f"release {label} attestation uses a different execution plan")
    if attestation.split is not split:
        raise ValueError(f"release {label} attestation uses the wrong split")
    if attestation.threshold_id != run.threshold_id:
        raise ValueError(f"release {label} attestation threshold id differs from bundle run")
    if float(attestation.threshold) != float(run.threshold):
        raise ValueError(f"release {label} attestation threshold value differs from bundle run")
    if attestation.execution_id != run.execution_id:
        raise ValueError(f"release {label} execution id differs from execution attestation")
    if attestation.target_manifest_sha256 != target_manifest.sha256():
        raise ValueError(f"release {label} attestation uses a different target manifest")

    prediction_path = _resolve_regular_file(release_artifact_root, run.prediction_artifact_path)
    raw = prediction_path.read_bytes()
    if sha256(raw).hexdigest() != attestation.prediction_artifact_sha256:
        raise ValueError(f"release {label} prediction bytes differ from execution attestation")
    predictions = load_extraction_prediction_artifact(prediction_path)
    if extraction_prediction_semantics_sha256(predictions) != attestation.prediction_semantics_sha256:
        raise ValueError(f"release {label} prediction semantics differ from execution attestation")


def _attestation_rows(value: object, *, label: str) -> tuple[ExtractionReleaseExecutionAttestationBinding, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"release execution binding {label} attestations must be non-empty")
    rows: list[ExtractionReleaseExecutionAttestationBinding] = []
    for index, row in enumerate(value):
        _require_exact_keys(
            row,
            _ATTESTATION_KEYS,
            label=f"release execution binding {label} attestation[{index}]",
        )
        rows.append(ExtractionReleaseExecutionAttestationBinding(**row))
    return tuple(rows)


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
        raise ValueError(f"release execution binding input must be a regular non-symlink file: {source}")
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


def _stable_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()
