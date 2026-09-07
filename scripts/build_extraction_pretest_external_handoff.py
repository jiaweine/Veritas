from __future__ import annotations

import argparse
import json
import re
from hashlib import sha256
from pathlib import Path

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SystemExit(f"{label} must be a lowercase SHA-256 digest")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic handoff manifest enumerating the exact pre-TEST bytes that an "
            "independently controlled historical channel must archive."
        )
    )
    parser.add_argument("--witness", type=Path, required=True)
    parser.add_argument("--sampling-frame", type=Path, required=True)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
    parser.add_argument("--pilot-threshold-policy", type=Path, required=True)
    parser.add_argument("--review-packet-commitment", type=Path, required=True)
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--parser-registry", type=Path, required=True)
    parser.add_argument("--numerical-runtime", type=Path, required=True)
    parser.add_argument("--execution-command", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    witness = _load_json(args.witness)
    if witness.get("schema_version") != 1:
        raise SystemExit("pre-TEST witness schema_version must be 1")
    if witness.get("status") != "repository_side_pretest_witness_commitment_awaiting_independent_anchor":
        raise SystemExit("pre-TEST witness is not in the expected repository-side pending-anchor state")
    for field in (
        "independent_external_anchor_present",
        "external_trust_root_pinned",
        "external_trust_policy_built",
        "trusted_commit_to_source_archive_provenance_established",
        "executed_v015_development_or_test_predictions",
        "production_authorized",
    ):
        if witness.get(field) is not False:
            raise SystemExit(f"pre-TEST witness must keep {field}=false")

    paths = {
        "sampling_frame": args.sampling_frame,
        "seed_manifest": args.seed_manifest,
        "evidence_plan": args.evidence_plan,
        "pilot_threshold_policy": args.pilot_threshold_policy,
        "review_packet_commitment": args.review_packet_commitment,
        "input_artifact_manifest": args.input_artifact_manifest,
        "execution_plan": args.execution_plan,
        "parser_registry": args.parser_registry,
        "numerical_runtime": args.numerical_runtime,
        "execution_command": args.execution_command,
    }
    observed = {name: _file_sha256(path) for name, path in paths.items()}

    expected = {
        "sampling_frame": witness["sampling_frame"]["json_file_sha256"],
        "seed_manifest": witness["seed_manifest"]["json_file_sha256"],
        "evidence_plan": witness["evidence_plan"]["json_file_sha256"],
        "pilot_threshold_policy": witness["pilot_threshold_policy"]["json_file_sha256"],
        "review_packet_commitment": witness["review_packets"]["commitment_json_file_sha256"],
        "input_artifact_manifest": witness["execution_artifacts"]["input_artifact_manifest_sha256"],
        "execution_plan": witness["execution_plan"]["json_file_sha256"],
        "parser_registry": witness["execution_artifacts"]["parser_registry_sha256"],
        "numerical_runtime": witness["execution_artifacts"]["numerical_runtime_sha256"],
        "execution_command": witness["execution_artifacts"]["execution_command_sha256"],
    }
    for name, expected_hash in expected.items():
        expected_hash = _require_sha256(expected_hash, label=f"witness {name} sha256")
        if observed[name] != expected_hash:
            raise SystemExit(f"{name} bytes differ from the pre-TEST witness commitment")

    input_manifest = _load_json(args.input_artifact_manifest)
    if input_manifest.get("production_authorized") is not False:
        raise SystemExit("input artifact manifest must remain non-production")
    publication_rows = input_manifest.get("artifacts")
    if not isinstance(publication_rows, list) or not publication_rows:
        raise SystemExit("input artifact manifest must contain publication artifacts")
    publications: list[dict[str, object]] = []
    for row in publication_rows:
        if not isinstance(row, dict):
            raise SystemExit("input artifact rows must be JSON objects")
        artifact_id = row.get("artifact_id")
        relative_path = row.get("relative_path")
        digest = _require_sha256(row.get("sha256"), label="publication sha256")
        size_bytes = row.get("size_bytes")
        if not isinstance(artifact_id, str) or not artifact_id:
            raise SystemExit("publication artifact_id must be non-empty")
        if not isinstance(relative_path, str) or not relative_path:
            raise SystemExit("publication relative_path must be non-empty")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 1:
            raise SystemExit("publication size_bytes must be a positive integer")
        publications.append(
            {
                "artifact_id": artifact_id,
                "relative_path": relative_path,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
        )
    publications.sort(key=lambda row: str(row["artifact_id"]))

    review = _load_json(args.review_packet_commitment)
    if review.get("distributed_to_human_reviewers") is not False:
        raise SystemExit("review packets must still be undistributed")
    if review.get("actual_reviewer_identities_assigned") is not False:
        raise SystemExit("actual reviewer identities must still be unassigned")
    packet_rows = review.get("reviewer_packets")
    if not isinstance(packet_rows, list) or len(packet_rows) != 2:
        raise SystemExit("review packet commitment must contain exactly two packet rows")
    packets: list[dict[str, object]] = []
    for row in packet_rows:
        if not isinstance(row, dict):
            raise SystemExit("review packet rows must be JSON objects")
        reviewer_slot = row.get("reviewer_slot")
        if reviewer_slot not in {"reviewer-a", "reviewer-b"}:
            raise SystemExit("review packet slots must be reviewer-a/reviewer-b")
        packets.append(
            {
                "reviewer_slot": reviewer_slot,
                "packet_sha256": _require_sha256(row.get("packet_sha256"), label="packet sha256"),
                "packet_file_sha256": _require_sha256(
                    row.get("packet_file_sha256"), label="packet file sha256"
                ),
                "target_count": row.get("target_count"),
            }
        )
    packets.sort(key=lambda row: str(row["reviewer_slot"]))

    repository_files = [
        {"path": str(path.as_posix()), "sha256": observed[name]}
        for name, path in paths.items()
    ]
    repository_files.append(
        {"path": str(args.witness.as_posix()), "sha256": _file_sha256(args.witness)}
    )
    repository_files.sort(key=lambda row: str(row["path"]))

    source_tree_sha256 = _require_sha256(
        witness["execution_artifacts"]["source_tree_sha256"], label="source tree sha256"
    )

    payload = {
        "schema_version": 1,
        "status": "repository_side_external_archive_handoff_ready_awaiting_independent_archive",
        "production_authorized": False,
        "pretest_witness": {
            "path": str(args.witness.as_posix()),
            "sha256": _file_sha256(args.witness),
        },
        "source_commit_sha": witness["source_commit_sha"],
        "repository_files": repository_files,
        "required_external_binary_artifacts": {
            "publication_inputs": publications,
            "blinded_reviewer_packets": packets,
            "source_tree": {
                "archive_name": "source-tree-v0.15.tar",
                "sha256": source_tree_sha256,
            },
        },
        "external_archive_requirements": {
            "preserve_exact_bytes": True,
            "independently_controlled_historical_channel_required": True,
            "immutable_or_append_only_record_required": True,
            "record_external_timestamp_or_sequence_position": True,
            "independently_select_expected_context_before_test": True,
            "do_not_copy_expected_context_from_future_signed_envelope": True,
            "pin_external_trust_root_before_test": True,
            "build_external_trust_policy_only_after_independent_root_selection": True,
            "preserve_source_archive_builder_identity_and_history_for_commit_to_archive_claim": True,
        },
        "pending_external_evidence": {
            "independent_archive_receipt_present": False,
            "external_trust_root_pinned": False,
            "external_trust_policy_built": False,
            "source_archive_trust_policy_built": False,
            "source_archive_provenance_statement_present": False,
            "source_archive_builder_history_preserved": False,
        },
        "executed_v015_development_or_test_predictions": False,
        "note": (
            "This repository-side handoff enumerates exact bytes/hashes for an independent pre-TEST "
            "archive. It is not an archive receipt, timestamp, trust root, trust policy, proof of "
            "key ownership, proof of workflow semantics, human review, TEST evidence, or production "
            "authorization."
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
