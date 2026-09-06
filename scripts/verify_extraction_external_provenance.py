from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
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
from veritas.extraction_release_source_binding import (
    verify_extraction_release_source_artifacts,
)


def _add_execution_artifact_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--input-artifact-root", type=Path, required=True)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--parser-registry", type=Path, required=True)
    parser.add_argument("--numerical-runtime", type=Path, required=True)
    parser.add_argument("--execution-command", type=Path, required=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cold-rebuild and verify archived extraction evidence against exact pre-TEST "
            "sources, plans, publication/execution bytes, trust policy, independently "
            "selected run context, and Ed25519 provenance."
        )
    )
    parser.add_argument("--sampling-frame", type=Path, required=True)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
    parser.add_argument("--release-bundle", type=Path, required=True)
    parser.add_argument("--release-artifact-root", type=Path, required=True)
    parser.add_argument("--trust-root", type=Path, required=True)
    parser.add_argument("--trust-policy", type=Path, required=True)
    parser.add_argument("--signed-provenance", type=Path, required=True)
    parser.add_argument("--execution-plan", type=Path, required=True)
    _add_execution_artifact_args(parser)
    parser.add_argument("--attested-release", type=Path, required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-run-attempt", type=int, required=True)
    parser.add_argument("--expected-commit-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sampling_frame = load_extraction_sampling_frame(args.sampling_frame)
    seed_manifest = load_extraction_seed_manifest(args.seed_manifest)
    evidence_plan, threshold_grid = load_extraction_evidence_plan(args.evidence_plan)
    release_bundle = load_extraction_release_evidence_bundle(args.release_bundle)
    trust_root = load_extraction_external_trust_root(args.trust_root)
    trust_policy = load_extraction_external_trust_policy(args.trust_policy)
    signed_provenance = load_extraction_signed_external_provenance(args.signed_provenance)
    execution_plan = load_extraction_execution_plan(args.execution_plan)
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
    payload = {
        "schema_version": 1,
        "release_bundle_sha256": release_bundle.sha256(),
        "rebuilt_attested_release_sha256": rebuilt_attested_release.sha256(),
        "receipt": asdict(receipt),
        "receipt_sha256": receipt.sha256(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(receipt.sha256())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
