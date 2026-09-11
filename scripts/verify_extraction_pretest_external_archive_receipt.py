from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from veritas.extraction_pretest_archive_receipt import (
    extraction_pretest_archive_object_set_sha256,
    verify_pretest_external_archive_receipt_binding,
)
from veritas.extraction_pretest_archive_receipt_json import (
    load_extraction_pretest_external_archive_receipt,
    verified_pretest_external_archive_receipt_binding_json_payload,
)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key is not allowed: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")


def _load_handoff(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("external archive handoff must be UTF-8 JSON") from exc
    payload = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_object_keys,
        parse_constant=_reject_json_constant,
    )
    if not isinstance(payload, dict):
        raise TypeError("external archive handoff root must be an object")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise TypeError("external archive handoff schema_version must be an integer")
    if schema_version != 1:
        raise ValueError("external archive handoff schema_version must be 1")
    if payload.get("status") != "repository_side_external_archive_handoff_ready_awaiting_independent_archive":
        raise ValueError("external archive handoff is not in the expected pending-independent-archive state")
    if payload.get("production_authorized") is not False:
        raise ValueError("external archive handoff must remain non-production")
    pending = payload.get("pending_external_evidence")
    if not isinstance(pending, dict):
        raise TypeError("external archive handoff pending_external_evidence must be an object")
    if pending.get("independent_archive_receipt_present") is not False:
        raise ValueError("repository-side handoff must not claim an external archive receipt")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that an externally supplied pre-TEST archive receipt binds the independently "
            "selected handoff/source/custodian/channel/record context. This verifies binding only; "
            "it does not establish independent control or historical-channel semantics."
        )
    )
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--expected-handoff-sha256", required=True)
    parser.add_argument("--expected-source-commit-sha", required=True)
    parser.add_argument("--expected-custodian-identity", required=True)
    parser.add_argument("--expected-archive-channel-identity", required=True)
    parser.add_argument("--expected-archive-record-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    actual_handoff_sha256 = _file_sha256(args.handoff)
    if actual_handoff_sha256 != args.expected_handoff_sha256:
        raise SystemExit("external archive handoff bytes differ from independently expected SHA-256")

    handoff = _load_handoff(args.handoff)
    source_commit_sha = handoff.get("source_commit_sha")
    if source_commit_sha != args.expected_source_commit_sha:
        raise SystemExit("external archive handoff source commit differs from independently expected commit")
    witness = handoff.get("pretest_witness")
    if not isinstance(witness, dict):
        raise SystemExit("external archive handoff pretest_witness must be an object")
    witness_sha256 = witness.get("sha256")
    if not isinstance(witness_sha256, str):
        raise SystemExit("external archive handoff pretest witness SHA-256 is missing")

    object_set_sha256 = extraction_pretest_archive_object_set_sha256(handoff)
    receipt_file_sha256 = _file_sha256(args.receipt)
    receipt = load_extraction_pretest_external_archive_receipt(args.receipt)
    verified = verify_pretest_external_archive_receipt_binding(
        receipt=receipt,
        expected_handoff_sha256=args.expected_handoff_sha256,
        expected_archived_object_set_sha256=object_set_sha256,
        expected_source_commit_sha=args.expected_source_commit_sha,
        expected_pretest_witness_sha256=witness_sha256,
        expected_custodian_identity=args.expected_custodian_identity,
        expected_archive_channel_identity=args.expected_archive_channel_identity,
        expected_archive_record_id=args.expected_archive_record_id,
    )
    payload = verified_pretest_external_archive_receipt_binding_json_payload(verified)
    payload["receipt_file_sha256"] = receipt_file_sha256
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
