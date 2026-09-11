from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_execution_artifacts import verify_extraction_execution_plan_artifacts
from veritas.extraction_execution_evidence_json import load_extraction_execution_plan
from veritas.extraction_external_provenance_json import load_extraction_external_trust_root
from veritas.extraction_external_trust_policy import build_extraction_external_trust_policy
from veritas.extraction_external_trust_policy_json import (
    extraction_external_trust_policy_json_payload,
)

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _source_commit(value: str) -> str:
    if not _GIT_SHA_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "source commit SHA must be 40 lowercase hexadecimal characters"
        )
    return value


def _add_execution_artifact_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--input-artifact-root", type=Path, required=True)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--parser-registry", type=Path, required=True)
    parser.add_argument("--numerical-runtime", type=Path, required=True)
    parser.add_argument("--execution-command", type=Path, required=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a pre-TEST trust policy for signed extraction provenance."
    )
    parser.add_argument("--policy-id", required=True)
    parser.add_argument(
        "--source-commit-sha",
        type=_source_commit,
        required=True,
        help="Exact source commit identity to freeze before held-out TEST evaluation.",
    )
    parser.add_argument(
        "--evidence-plan",
        required=True,
        type=Path,
        help=(
            "Strict JSON ExtractionEvidencePlan archive emitted by "
            "build_extraction_evidence_plan.py. Its SHA-256 is recomputed, not supplied manually."
        ),
    )
    parser.add_argument(
        "--execution-plan",
        required=True,
        type=Path,
        help=(
            "Strict JSON ExtractionExecutionPlan archive frozen before TEST. "
            "Its SHA-256 and all publication/execution artifact commitments are recomputed."
        ),
    )
    _add_execution_artifact_args(parser)
    parser.add_argument(
        "--trust-root",
        required=True,
        type=Path,
        help="Strict JSON ExtractionExternalTrustRoot manifest to pin before TEST.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    evidence_plan, _ = load_extraction_evidence_plan(args.evidence_plan)
    execution_plan = load_extraction_execution_plan(args.execution_plan)
    verify_extraction_execution_plan_artifacts(
        execution_plan,
        input_artifact_manifest=args.input_artifact_manifest,
        input_artifact_root=args.input_artifact_root,
        source_tree=args.source_tree,
        parser_registry=args.parser_registry,
        numerical_runtime=args.numerical_runtime,
        execution_command=args.execution_command,
    )
    trust_root = load_extraction_external_trust_root(args.trust_root)
    policy = build_extraction_external_trust_policy(
        policy_id=args.policy_id,
        evidence_plan_sha256=evidence_plan.sha256(),
        execution_plan=execution_plan,
        source_commit_sha=args.source_commit_sha,
        trust_root=trust_root,
    )
    payload = extraction_external_trust_policy_json_payload(policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(policy.sha256())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
