from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify archived extraction execution evidence against a pre-TEST trust policy, "
            "independently selected run context, and an Ed25519-signed provenance envelope."
        )
    )
    parser.add_argument("--trust-root", type=Path, required=True)
    parser.add_argument("--trust-policy", type=Path, required=True)
    parser.add_argument("--signed-provenance", type=Path, required=True)
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--attested-release", type=Path, required=True)
    parser.add_argument("--evidence-plan-sha256", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-run-attempt", type=int, required=True)
    parser.add_argument("--expected-commit-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    trust_root = load_extraction_external_trust_root(args.trust_root)
    trust_policy = load_extraction_external_trust_policy(args.trust_policy)
    signed_provenance = load_extraction_signed_external_provenance(args.signed_provenance)
    execution_plan = load_extraction_execution_plan(args.execution_plan)
    attested_release = load_attested_extraction_evidence_release_receipt(args.attested_release)

    receipt = verify_precommitted_external_extraction_provenance_for_run(
        trust_policy=trust_policy,
        evidence_plan_sha256=args.evidence_plan_sha256,
        trust_root=trust_root,
        signed_provenance=signed_provenance,
        attested_release_receipt=attested_release,
        execution_plan=execution_plan,
        expected_run_id=args.expected_run_id,
        expected_run_attempt=args.expected_run_attempt,
        expected_commit_sha=args.expected_commit_sha,
    )
    payload = {
        "schema_version": 1,
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
