from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_execution_evidence_json import load_extraction_execution_plan
from veritas.extraction_external_provenance_json import load_extraction_external_trust_root
from veritas.extraction_external_trust_policy import build_extraction_external_trust_policy
from veritas.extraction_external_trust_policy_json import (
    extraction_external_trust_policy_json_payload,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a pre-TEST trust policy for signed extraction provenance."
    )
    parser.add_argument("--policy-id", required=True)
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
            "Its SHA-256 is recomputed and committed by the trust policy."
        ),
    )
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
    trust_root = load_extraction_external_trust_root(args.trust_root)
    policy = build_extraction_external_trust_policy(
        policy_id=args.policy_id,
        evidence_plan_sha256=evidence_plan.sha256(),
        execution_plan=execution_plan,
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
