from __future__ import annotations

import argparse
import json
import re
from hashlib import sha256
from pathlib import Path

from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_execution_artifacts import verify_extraction_execution_plan_artifacts
from veritas.extraction_execution_evidence_json import load_extraction_execution_plan

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic repository-side pre-TEST witness commitment that can be "
            "anchored later by an independent historical channel."
        )
    )
    parser.add_argument("--source-commit-sha", required=True)
    parser.add_argument("--sampling-frame", type=Path, required=True)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
    parser.add_argument("--pilot-threshold-policy", type=Path, required=True)
    parser.add_argument("--review-packet-commitment", type=Path, required=True)
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--input-artifact-root", type=Path, required=True)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--parser-registry", type=Path, required=True)
    parser.add_argument("--numerical-runtime", type=Path, required=True)
    parser.add_argument("--execution-command", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not _GIT_SHA_RE.fullmatch(args.source_commit_sha):
        raise SystemExit("source commit SHA must be 40 lowercase hexadecimal characters")

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

    evidence_plan_payload = _load_json(args.evidence_plan)
    pilot_policy = _load_json(args.pilot_threshold_policy)
    review_commitment = _load_json(args.review_packet_commitment)

    if evidence_plan_payload.get("plan_sha256") != evidence_plan.sha256():
        raise SystemExit("evidence-plan JSON self-commitment differs from canonical plan identity")
    if pilot_policy.get("bound_evidence_plan_sha256") != evidence_plan.sha256():
        raise SystemExit("pilot threshold policy is bound to a different evidence plan")
    if pilot_policy.get("production_authorized") is not False:
        raise SystemExit("pilot threshold policy must remain non-production")
    if review_commitment.get("distributed_to_human_reviewers") is not False:
        raise SystemExit("review packets must remain undistributed while building pre-TEST witness")
    if review_commitment.get("actual_reviewer_identities_assigned") is not False:
        raise SystemExit("reviewer identities must remain unassigned while building pre-TEST witness")

    artifact_hashes = {
        "source_tree_sha256": _file_sha256(args.source_tree),
        "parser_registry_sha256": _file_sha256(args.parser_registry),
        "numerical_runtime_sha256": _file_sha256(args.numerical_runtime),
        "execution_command_sha256": _file_sha256(args.execution_command),
        "input_artifact_manifest_sha256": _file_sha256(args.input_artifact_manifest),
    }
    for field, observed in artifact_hashes.items():
        expected = getattr(execution_plan, field)
        if observed != expected:
            raise SystemExit(f"{field} differs from frozen execution plan")

    packet_rows = review_commitment.get("reviewer_packets")
    if not isinstance(packet_rows, list) or len(packet_rows) != 2:
        raise SystemExit("review-packet commitment must contain exactly two reviewer slots")
    packet_hashes = {
        str(row["reviewer_slot"]): str(row["packet_sha256"])
        for row in packet_rows
        if isinstance(row, dict)
    }
    if set(packet_hashes) != {"reviewer-a", "reviewer-b"}:
        raise SystemExit("review-packet commitment must contain reviewer-a and reviewer-b")

    payload = {
        "schema_version": 1,
        "status": "repository_side_pretest_witness_commitment_awaiting_independent_anchor",
        "production_authorized": False,
        "source_commit_sha": args.source_commit_sha,
        "sampling_frame": {
            "json_file_sha256": _file_sha256(args.sampling_frame),
            "normalized_sha256": evidence_plan.sampling_frame_sha256,
        },
        "seed_manifest": {
            "json_file_sha256": _file_sha256(args.seed_manifest),
            "target_universe_sha256": evidence_plan.seed_target_universe_sha256,
        },
        "evidence_plan": {
            "canonical_sha256": evidence_plan.sha256(),
            "json_file_sha256": _file_sha256(args.evidence_plan),
            "threshold_grid_sha256": evidence_plan.threshold_grid_sha256,
        },
        "pilot_threshold_policy": {
            "policy_sha256": str(pilot_policy["threshold_policy_sha256"]),
            "json_file_sha256": _file_sha256(args.pilot_threshold_policy),
        },
        "review_packets": {
            "reviewer_a_packet_sha256": packet_hashes["reviewer-a"],
            "reviewer_b_packet_sha256": packet_hashes["reviewer-b"],
            "commitment_json_file_sha256": _file_sha256(args.review_packet_commitment),
        },
        "execution_plan": {
            "canonical_sha256": execution_plan.sha256(),
            "json_file_sha256": _file_sha256(args.execution_plan),
        },
        "execution_artifacts": artifact_hashes,
        "isolation_contract": {
            "network_disabled": execution_plan.network_disabled,
            "source_mount_read_only": execution_plan.source_mount_read_only,
            "credentials_mounted": execution_plan.credentials_mounted,
        },
        "independent_external_anchor_present": False,
        "external_trust_root_pinned": False,
        "external_trust_policy_built": False,
        "trusted_commit_to_source_archive_provenance_established": False,
        "executed_v015_development_or_test_predictions": False,
        "note": (
            "This deterministic commitment packages repository-side pre-TEST identities for later "
            "independent historical anchoring. It does not itself establish independent governance, "
            "trusted key ownership, an external trust root/policy, commit-to-source-archive provenance, "
            "human review, DEVELOPMENT calibration, TEST evaluation, or production authority."
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
