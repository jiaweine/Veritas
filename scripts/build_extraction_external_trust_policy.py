from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from veritas.extraction_external_provenance_json import load_extraction_external_trust_root
from veritas.extraction_external_trust_policy import build_extraction_external_trust_policy
from veritas.extraction_external_trust_policy_json import (
    extraction_external_trust_policy_json_payload,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256(value: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("evidence plan SHA-256 must be 64 lowercase hex characters")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a pre-TEST trust policy for signed extraction provenance."
    )
    parser.add_argument("--policy-id", required=True)
    parser.add_argument(
        "--evidence-plan-sha256",
        required=True,
        type=_sha256,
        help="SHA-256 of the already-frozen ExtractionEvidencePlan.",
    )
    parser.add_argument(
        "--trust-root",
        required=True,
        type=Path,
        help="Strict JSON ExtractionExternalTrustRoot manifest to pin before TEST.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    trust_root = load_extraction_external_trust_root(args.trust_root)
    policy = build_extraction_external_trust_policy(
        policy_id=args.policy_id,
        evidence_plan_sha256=args.evidence_plan_sha256,
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
