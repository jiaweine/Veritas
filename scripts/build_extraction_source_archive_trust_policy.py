from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from veritas.extraction_execution_artifacts import extraction_execution_artifact_sha256
from veritas.extraction_execution_evidence_json import load_extraction_execution_plan
from veritas.extraction_external_provenance_json import load_extraction_external_trust_root
from veritas.extraction_source_archive_provenance import (
    build_extraction_source_archive_trust_policy,
)
from veritas.extraction_source_archive_provenance_json import (
    extraction_source_archive_trust_policy_json_payload,
)

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _source_commit(value: str) -> str:
    if not _GIT_SHA_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "source commit SHA must be 40 lowercase hexadecimal characters"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a pre-TEST trust policy for a trusted source-archive build relation."
        )
    )
    parser.add_argument("--policy-id", required=True)
    parser.add_argument(
        "--source-commit-sha",
        type=_source_commit,
        required=True,
        help="Exact Git commit the trusted builder must attest as the archive input.",
    )
    parser.add_argument(
        "--execution-plan",
        required=True,
        type=Path,
        help="Strict ExtractionExecutionPlan JSON containing the frozen source-tree digest.",
    )
    parser.add_argument(
        "--source-tree",
        required=True,
        type=Path,
        help="Exact source-tree archive bytes committed by the execution plan.",
    )
    parser.add_argument(
        "--trust-root",
        required=True,
        type=Path,
        help="Strict ExtractionExternalTrustRoot JSON for the trusted archive builder.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    execution_plan = load_extraction_execution_plan(args.execution_plan)
    if extraction_execution_artifact_sha256(args.source_tree) != execution_plan.source_tree_sha256:
        raise ValueError("execution plan source tree differs from archived artifact bytes")
    trust_root = load_extraction_external_trust_root(args.trust_root)
    policy = build_extraction_source_archive_trust_policy(
        policy_id=args.policy_id,
        execution_plan=execution_plan,
        source_commit_sha=args.source_commit_sha,
        trust_root=trust_root,
    )
    payload = extraction_source_archive_trust_policy_json_payload(policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(policy.sha256())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
