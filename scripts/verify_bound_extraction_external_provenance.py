from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

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
from veritas.extraction_input_artifacts import load_extraction_input_artifact_manifest
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


def _file_sha256(path: str | Path) -> str:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"bound cold-verification input must be a regular non-symlink file: {source}")
    digest = sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _attestation_map(values: list[list[str]], *, label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for threshold_id, path_text in values:
        if threshold_id in result:
            raise ValueError(f"duplicate {label} attestation threshold id: {threshold_id!r}")
        result[threshold_id] = Path(path_text)
    return result


def _add_execution_artifact_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--input-artifact-root", type=Path, required=True)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--parser-registry", type=Path, required=True)
    parser.add_argument("--numerical-runtime", type=Path, required=True)
    parser.add_argument("--execution-command", type=Path, required=True)


def _add_optional_source_archive_provenance_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-archive-trust-root", type=Path)
    parser.add_argument("--source-archive-trust-policy", type=Path)
    parser.add_argument("--signed-source-archive-provenance", type=Path)
    parser.add_argument("--expected-source-archive-run-id")
    parser.add_argument("--expected-source-archive-run-attempt", type=int)


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
            "source archive provenance verification requires trust root, trust policy, signed "
            "provenance, expected run id, and expected run attempt together"
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the exact calibration and execution-attestation release bindings in the same "
            "process that cold-rebuilds and verifies external extraction provenance. This is the "
            "v0.15 bound-release verifier; the older unbound verifier remains a compatibility path."
        )
    )
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
    _add_execution_artifact_args(parser)
    parser.add_argument("--attested-release", type=Path, required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-run-attempt", type=int, required=True)
    parser.add_argument("--expected-commit-sha", required=True)
    _add_optional_source_archive_provenance_args(parser)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sampling_frame = load_extraction_sampling_frame(args.sampling_frame)
    seed_manifest = load_extraction_seed_manifest(args.seed_manifest)
    evidence_plan, threshold_grid = load_extraction_evidence_plan(args.evidence_plan)
    release_bundle = load_extraction_release_evidence_bundle(args.release_bundle)

    pilot_policy = load_pretest_pilot_threshold_policy(args.pilot_threshold_policy)
    development_freeze = load_development_calibration_freeze(args.development_freeze)
    development_manifest = load_extraction_split_target_manifest(args.development_manifest)
    test_evaluation_archive = load_test_evaluation_archive(args.test_evaluation_lock)
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
        test_evaluation_archive=test_evaluation_archive,
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

    input_artifact_manifest = load_extraction_input_artifact_manifest(
        args.input_artifact_manifest
    )
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
        input_artifact_manifest,
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

    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "bound_external_provenance_verified",
        "production_authorized": False,
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

    if _source_archive_args_are_complete(args):
        source_archive_trust_root = load_extraction_external_trust_root(
            args.source_archive_trust_root
        )
        source_archive_trust_policy = load_extraction_source_archive_trust_policy(
            args.source_archive_trust_policy
        )
        signed_source_archive_provenance = (
            load_extraction_signed_source_archive_provenance(
                args.signed_source_archive_provenance
            )
        )
        source_archive_receipt = (
            verify_precommitted_extraction_source_archive_provenance_for_run(
                trust_policy=source_archive_trust_policy,
                trust_root=source_archive_trust_root,
                signed_provenance=signed_source_archive_provenance,
                execution_plan=execution_plan,
                expected_run_id=args.expected_source_archive_run_id,
                expected_run_attempt=args.expected_source_archive_run_attempt,
                expected_commit_sha=args.expected_commit_sha,
            )
        )
        payload["source_archive_receipt"] = asdict(source_archive_receipt)
        payload["source_archive_receipt_sha256"] = source_archive_receipt.sha256()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(receipt.sha256())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
