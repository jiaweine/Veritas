from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from veritas.extraction_calibration_archive import (
    load_development_calibration_freeze,
    load_pretest_pilot_threshold_policy,
    load_test_evaluation_archive,
)
from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_evidence_workflow import (
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)
from veritas.extraction_execution_artifacts import verify_extraction_execution_plan_artifacts
from veritas.extraction_execution_evidence_json import (
    load_attested_extraction_evidence_release_receipt,
    load_extraction_execution_plan,
)
from veritas.extraction_external_provenance_json import (
    load_extraction_external_trust_root,
    load_extraction_signed_external_provenance,
)
from veritas.extraction_external_trust_policy import (
    verify_precommitted_external_extraction_provenance_for_run,
)
from veritas.extraction_external_trust_policy_json import (
    load_extraction_external_trust_policy,
)
from veritas.extraction_input_artifacts import (
    load_extraction_input_artifact_manifest,
    verify_extraction_input_artifact_manifest,
)
from veritas.extraction_release_archive import (
    load_extraction_release_evidence_bundle,
    rebuild_attested_extraction_evidence_release_receipt_from_archive,
)
from veritas.extraction_release_calibration_binding import (
    load_extraction_release_calibration_binding,
    verify_extraction_release_calibration_binding,
)
from veritas.extraction_release_execution_binding import (
    load_extraction_release_execution_binding,
    verify_extraction_release_execution_binding,
)
from veritas.extraction_release_source_binding import verify_extraction_release_source_artifacts
from veritas.extraction_source_archive_provenance import (
    verify_precommitted_extraction_source_archive_provenance_for_run,
)
from veritas.extraction_source_archive_provenance_json import (
    load_extraction_signed_source_archive_provenance,
    load_extraction_source_archive_trust_policy,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BOUND_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "production_authorized",
        "release_bundle_sha256",
        "release_bundle_file_sha256",
        "release_calibration_binding_sha256",
        "release_calibration_binding_file_sha256",
        "release_execution_binding_sha256",
        "release_execution_binding_file_sha256",
        "rebuilt_attested_release_sha256",
        "receipt",
        "receipt_sha256",
    }
)
_BOUND_SOURCE_ARCHIVE_KEYS = frozenset(
    {"source_archive_receipt", "source_archive_receipt_sha256"}
)


def _file_sha256(path: str | Path) -> str:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"archive input must be a regular non-symlink file: {source}")
    digest = sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
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
        raise ValueError(f"{label} contains non-standard JSON number: {value}")

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
    return raw, payload


def _load_bound_verification(path: Path) -> dict[str, Any]:
    raw, payload = _strict_json(path, label="bound cold-verification artifact")
    actual_keys = frozenset(payload)
    if actual_keys not in {
        _BOUND_REQUIRED_KEYS,
        _BOUND_REQUIRED_KEYS | _BOUND_SOURCE_ARCHIVE_KEYS,
    }:
        raise ValueError("bound cold-verification artifact keys differ from schema")
    if payload["schema_version"] != 1 or isinstance(payload["schema_version"], bool):
        raise ValueError("bound cold-verification schema_version must be integer 1")
    if payload["status"] != "bound_external_provenance_verified":
        raise ValueError("bound cold-verification artifact is not verified")
    if payload["production_authorized"] is not False:
        raise ValueError("bound cold-verification artifact must remain non-production")
    canonical = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise ValueError("bound cold-verification artifact bytes are not canonical JSON")
    for key in (
        "release_bundle_sha256",
        "release_bundle_file_sha256",
        "release_calibration_binding_sha256",
        "release_calibration_binding_file_sha256",
        "release_execution_binding_sha256",
        "release_execution_binding_file_sha256",
        "rebuilt_attested_release_sha256",
        "receipt_sha256",
    ):
        _require_sha256(payload[key], label=f"bound verification {key}")
    if "source_archive_receipt_sha256" in payload:
        _require_sha256(
            payload["source_archive_receipt_sha256"],
            label="bound verification source_archive_receipt_sha256",
        )
    return payload


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _attestation_map(values: list[list[str]], *, label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for threshold_id, path_text in values:
        if threshold_id in result:
            raise ValueError(f"duplicate {label} attestation threshold id: {threshold_id!r}")
        result[threshold_id] = Path(path_text)
    return result


def _validated_root(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symbolic link")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    return resolved


def _resolve_regular_file(root: Path, relative_path: str, *, label: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError(f"{label} relative path must be non-empty")
    if "\\" in relative_path or relative_path.startswith("/"):
        raise ValueError(f"{label} relative path must be safe POSIX relative path")
    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} relative path must be safe POSIX relative path")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} path must not contain symbolic links")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f"{label} path escapes configured root")
    if not resolved.is_file():
        raise ValueError(f"{label} path must reference a regular file")
    return resolved


def _archive_object(archive_name: str, path: Path) -> dict[str, object]:
    if not archive_name or archive_name.startswith("/") or "\\" in archive_name:
        raise ValueError("archive_name must be a safe POSIX relative path")
    if any(part in {"", ".", ".."} for part in archive_name.split("/")):
        raise ValueError("archive_name must be a safe POSIX relative path")
    return {
        "archive_name": archive_name,
        "source_path": path.as_posix(),
        "sha256": _file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _archive_object_set_sha256(rows: list[dict[str, object]]) -> str:
    stable_rows = [
        {
            "archive_name": row["archive_name"],
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
        }
        for row in rows
    ]
    raw = json.dumps(
        stable_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _source_archive_args_are_complete(args: argparse.Namespace) -> bool:
    values = (
        args.source_archive_trust_root,
        args.source_archive_trust_policy,
        args.signed_source_archive_provenance,
        args.expected_source_archive_run_id,
        args.expected_source_archive_run_attempt,
    )
    if all(value is None for value in values):
        return False
    if any(value is None for value in values):
        raise ValueError(
            "source archive provenance requires trust root, trust policy, signed provenance, "
            "expected run id, and expected run attempt together"
        )
    return True


def _add_source_archive_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-archive-trust-root", type=Path)
    parser.add_argument("--source-archive-trust-policy", type=Path)
    parser.add_argument("--signed-source-archive-provenance", type=Path)
    parser.add_argument("--expected-source-archive-run-id")
    parser.add_argument("--expected-source-archive-run-attempt", type=int)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a repository-side post-verification handoff containing the exact bytes needed "
            "to independently replay the v0.15 bound cold verification. The output is awaiting an "
            "independently controlled external archive and is not itself an external receipt."
        )
    )
    parser.add_argument("--bound-verification", type=Path, required=True)
    parser.add_argument("--sampling-frame", type=Path, required=True)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
    parser.add_argument("--release-bundle", type=Path, required=True)
    parser.add_argument("--release-artifact-root", type=Path, required=True)
    parser.add_argument("--release-calibration-binding", type=Path, required=True)
    parser.add_argument("--pilot-threshold-policy", type=Path, required=True)
    parser.add_argument("--development-freeze", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--test-evaluation-lock", type=Path, required=True)
    parser.add_argument("--test-manifest", type=Path, required=True)
    parser.add_argument("--release-execution-binding", type=Path, required=True)
    parser.add_argument(
        "--development-attestation",
        nargs=2,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "ATTESTATION_PATH"),
    )
    parser.add_argument(
        "--test-attestation",
        nargs=2,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "ATTESTATION_PATH"),
    )
    parser.add_argument("--trust-root", type=Path, required=True)
    parser.add_argument("--trust-policy", type=Path, required=True)
    parser.add_argument("--signed-provenance", type=Path, required=True)
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--input-artifact-root", type=Path, required=True)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--parser-registry", type=Path, required=True)
    parser.add_argument("--numerical-runtime", type=Path, required=True)
    parser.add_argument("--execution-command", type=Path, required=True)
    parser.add_argument("--attested-release", type=Path, required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-run-attempt", type=int, required=True)
    parser.add_argument("--expected-commit-sha", required=True)
    _add_source_archive_args(parser)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    bound = _load_bound_verification(args.bound_verification)
    sampling_frame = load_extraction_sampling_frame(args.sampling_frame)
    seed_manifest = load_extraction_seed_manifest(args.seed_manifest)
    evidence_plan, threshold_grid = load_extraction_evidence_plan(args.evidence_plan)
    release_bundle = load_extraction_release_evidence_bundle(args.release_bundle)
    pilot_policy = load_pretest_pilot_threshold_policy(args.pilot_threshold_policy)
    development_freeze = load_development_calibration_freeze(args.development_freeze)
    development_manifest = load_extraction_split_target_manifest(args.development_manifest)
    test_archive = load_test_evaluation_archive(args.test_evaluation_lock)
    test_manifest = load_extraction_split_target_manifest(args.test_manifest)
    calibration_binding = load_extraction_release_calibration_binding(
        args.release_calibration_binding
    )
    execution_plan = load_extraction_execution_plan(args.execution_plan)
    execution_binding = load_extraction_release_execution_binding(
        args.release_execution_binding
    )
    development_attestations = _attestation_map(
        args.development_attestation, label="DEVELOPMENT"
    )
    test_attestations = _attestation_map(args.test_attestation, label="TEST")

    verify_extraction_release_calibration_binding(
        calibration_binding,
        bundle=release_bundle,
        bundle_path=args.release_bundle,
        plan=evidence_plan,
        threshold_grid_sha256=threshold_grid.sha256(),
        pilot_policy=pilot_policy,
        pilot_policy_path=args.pilot_threshold_policy,
        development_freeze=development_freeze,
        development_freeze_path=args.development_freeze,
        development_manifest=development_manifest,
        development_manifest_path=args.development_manifest,
        test_evaluation_archive=test_archive,
        test_evaluation_archive_path=args.test_evaluation_lock,
        test_manifest=test_manifest,
        test_manifest_path=args.test_manifest,
        release_artifact_root=args.release_artifact_root,
    )
    verify_extraction_release_execution_binding(
        execution_binding,
        bundle=release_bundle,
        bundle_path=args.release_bundle,
        execution_plan=execution_plan,
        execution_plan_path=args.execution_plan,
        development_manifest=development_manifest,
        test_manifest=test_manifest,
        release_artifact_root=args.release_artifact_root,
        development_attestation_paths=development_attestations,
        test_attestation_paths=test_attestations,
    )

    input_manifest = load_extraction_input_artifact_manifest(args.input_artifact_manifest)
    verify_extraction_input_artifact_manifest(input_manifest, args.input_artifact_root)
    verify_extraction_execution_plan_artifacts(
        execution_plan,
        input_artifact_manifest=args.input_artifact_manifest,
        input_artifact_root=args.input_artifact_root,
        source_tree=args.source_tree,
        parser_registry=args.parser_registry,
        numerical_runtime=args.numerical_runtime,
        execution_command=args.execution_command,
    )
    verify_extraction_release_source_artifacts(
        release_bundle,
        input_manifest,
        release_artifact_root=args.release_artifact_root,
    )

    archived_attested_release = load_attested_extraction_evidence_release_receipt(
        args.attested_release
    )
    rebuilt_attested_release = (
        rebuild_attested_extraction_evidence_release_receipt_from_archive(
            release_bundle,
            release_artifact_root=args.release_artifact_root,
            plan=evidence_plan,
            sampling_frame=sampling_frame,
            seed_manifest=seed_manifest,
            threshold_grid=threshold_grid,
            execution_plan=execution_plan,
        )
    )
    if archived_attested_release != rebuilt_attested_release:
        raise ValueError(
            "archived attested release differs from release rebuilt from source evidence"
        )

    trust_root = load_extraction_external_trust_root(args.trust_root)
    trust_policy = load_extraction_external_trust_policy(args.trust_policy)
    signed_provenance = load_extraction_signed_external_provenance(args.signed_provenance)
    receipt = verify_precommitted_external_extraction_provenance_for_run(
        trust_policy=trust_policy,
        evidence_plan_sha256=evidence_plan.sha256(),
        trust_root=trust_root,
        signed_provenance=signed_provenance,
        attested_release_receipt=rebuilt_attested_release,
        execution_plan=execution_plan,
        expected_run_id=args.expected_run_id,
        expected_run_attempt=args.expected_run_attempt,
        expected_commit_sha=args.expected_commit_sha,
    )

    expected_bound = {
        "release_bundle_sha256": release_bundle.sha256(),
        "release_bundle_file_sha256": _file_sha256(args.release_bundle),
        "release_calibration_binding_sha256": calibration_binding.sha256(),
        "release_calibration_binding_file_sha256": _file_sha256(
            args.release_calibration_binding
        ),
        "release_execution_binding_sha256": execution_binding.sha256(),
        "release_execution_binding_file_sha256": _file_sha256(
            args.release_execution_binding
        ),
        "rebuilt_attested_release_sha256": rebuilt_attested_release.sha256(),
        "receipt": asdict(receipt),
        "receipt_sha256": receipt.sha256(),
    }
    for key, expected in expected_bound.items():
        if bound[key] != expected:
            raise ValueError(f"bound cold-verification artifact differs from supplied inputs: {key}")

    source_archive_receipt = None
    source_archive_complete = _source_archive_args_are_complete(args)
    bound_has_source_archive = "source_archive_receipt" in bound
    if source_archive_complete != bound_has_source_archive:
        raise ValueError(
            "source archive verification inputs must match the bound verification artifact scope"
        )
    if source_archive_complete:
        source_archive_trust_root = load_extraction_external_trust_root(
            args.source_archive_trust_root
        )
        source_archive_trust_policy = load_extraction_source_archive_trust_policy(
            args.source_archive_trust_policy
        )
        signed_source_archive = load_extraction_signed_source_archive_provenance(
            args.signed_source_archive_provenance
        )
        source_archive_receipt = (
            verify_precommitted_extraction_source_archive_provenance_for_run(
                trust_policy=source_archive_trust_policy,
                trust_root=source_archive_trust_root,
                signed_provenance=signed_source_archive,
                execution_plan=execution_plan,
                expected_run_id=args.expected_source_archive_run_id,
                expected_run_attempt=args.expected_source_archive_run_attempt,
                expected_commit_sha=args.expected_commit_sha,
            )
        )
        if bound["source_archive_receipt"] != asdict(source_archive_receipt):
            raise ValueError("bound source archive receipt differs from supplied inputs")
        if bound["source_archive_receipt_sha256"] != source_archive_receipt.sha256():
            raise ValueError("bound source archive receipt SHA-256 differs from supplied inputs")

    objects: list[dict[str, object]] = []
    control_paths = {
        "verification/bound-cold-verification.json": args.bound_verification,
        "source/sampling-frame.json": args.sampling_frame,
        "source/seed-manifest.json": args.seed_manifest,
        "plans/evidence-plan.json": args.evidence_plan,
        "release/release-evidence-bundle.json": args.release_bundle,
        "release/release-calibration-binding.json": args.release_calibration_binding,
        "calibration/pilot-threshold-policy.json": args.pilot_threshold_policy,
        "calibration/development-calibration-freeze.json": args.development_freeze,
        "manifests/development-target-manifest.json": args.development_manifest,
        "calibration/test-evaluation-lock.json": args.test_evaluation_lock,
        "manifests/test-target-manifest.json": args.test_manifest,
        "release/release-execution-binding.json": args.release_execution_binding,
        "provenance/trust-root.json": args.trust_root,
        "provenance/trust-policy.json": args.trust_policy,
        "provenance/signed-external-provenance.json": args.signed_provenance,
        "plans/execution-plan.json": args.execution_plan,
        "execution/input-artifact-manifest.json": args.input_artifact_manifest,
        "execution/parser-registry.json": args.parser_registry,
        "execution/numerical-runtime.json": args.numerical_runtime,
        "execution/execution-command.json": args.execution_command,
        "release/attested-release.json": args.attested_release,
        "execution/source-tree.tar": args.source_tree,
    }
    for archive_name, path in control_paths.items():
        objects.append(_archive_object(archive_name, path))

    for threshold_id, path in sorted(development_attestations.items()):
        objects.append(
            _archive_object(f"attestations/development/{threshold_id}.json", path)
        )
    for threshold_id, path in sorted(test_attestations.items()):
        objects.append(_archive_object(f"attestations/test/{threshold_id}.json", path))

    release_root = _validated_root(args.release_artifact_root, label="release artifact root")
    for split_name, runs in (
        ("development", release_bundle.development_runs),
        ("test", release_bundle.test_runs),
    ):
        for run in sorted(runs, key=lambda item: item.threshold_id):
            path = _resolve_regular_file(
                release_root,
                run.prediction_artifact_path,
                label="release prediction artifact",
            )
            objects.append(
                _archive_object(
                    f"predictions/{split_name}/{run.threshold_id}.json",
                    path,
                )
            )

    input_root = _validated_root(args.input_artifact_root, label="input artifact root")
    for artifact in sorted(input_manifest.artifacts, key=lambda item: item.artifact_id):
        path = _resolve_regular_file(
            input_root,
            artifact.relative_path,
            label="publication input artifact",
        )
        objects.append(
            _archive_object(f"publication-inputs/{artifact.relative_path}", path)
        )

    if source_archive_complete:
        for archive_name, path in (
            ("source-archive/trust-root.json", args.source_archive_trust_root),
            ("source-archive/trust-policy.json", args.source_archive_trust_policy),
            (
                "source-archive/signed-provenance.json",
                args.signed_source_archive_provenance,
            ),
        ):
            objects.append(_archive_object(archive_name, path))

    objects.sort(key=lambda row: str(row["archive_name"]))
    archive_names = [str(row["archive_name"]) for row in objects]
    source_paths = [str(row["source_path"]) for row in objects]
    if len(set(archive_names)) != len(archive_names):
        raise ValueError("post-verification archive names must be unique")
    if len(set(source_paths)) != len(source_paths):
        raise ValueError("post-verification archive source paths must be unique")

    payload = {
        "schema_version": 1,
        "status": (
            "repository_side_postverification_external_archive_handoff_ready_"
            "awaiting_independent_archive"
        ),
        "production_authorized": False,
        "source_commit_sha": args.expected_commit_sha,
        "bound_verification": {
            "file_sha256": _file_sha256(args.bound_verification),
            "receipt_sha256": receipt.sha256(),
            "release_bundle_sha256": release_bundle.sha256(),
            "release_calibration_binding_sha256": calibration_binding.sha256(),
            "release_execution_binding_sha256": execution_binding.sha256(),
            "rebuilt_attested_release_sha256": rebuilt_attested_release.sha256(),
        },
        "external_provenance": {
            "trust_root_sha256": trust_root.sha256(),
            "trust_policy_sha256": trust_policy.sha256(),
            "signed_provenance_sha256": signed_provenance.sha256(),
            "signed_provenance_file_sha256": _file_sha256(args.signed_provenance),
            "expected_run_id": args.expected_run_id,
            "expected_run_attempt": args.expected_run_attempt,
            "expected_commit_sha": args.expected_commit_sha,
            "original_signed_statement_directly_commits_release_sidecars": False,
        },
        "source_archive_verification": (
            {
                "receipt_sha256": source_archive_receipt.sha256(),
                "included": True,
            }
            if source_archive_receipt is not None
            else {"included": False}
        ),
        "archive_objects": objects,
        "archive_object_set_sha256": _archive_object_set_sha256(objects),
        "external_archive_requirements": {
            "preserve_exact_bytes": True,
            "independently_controlled_channel_required": True,
            "immutable_or_append_only_record_required": True,
            "record_external_timestamp_or_sequence_position": True,
            "archive_bound_verification_and_both_release_sidecars_together": True,
            "rerun_bound_cold_verification_from_archived_objects": True,
            "do_not_recharacterize_original_signature_scope": True,
        },
        "pending_external_evidence": {
            "independent_archive_receipt_present": False,
            "independent_control_established": False,
            "historical_channel_semantics_established": False,
        },
        "note": (
            "This repository-side handoff is created after bound cold verification. It packages "
            "the exact replay inputs, both release sidecars, and the original signed provenance for "
            "a later independently controlled archive event. It is not an external receipt, does not "
            "retroactively expand the scope of the original signature, and does not prove reviewer "
            "independence, historical custody, untouched TEST handling, key/workflow ownership, or "
            "production authority."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(_file_sha256(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
