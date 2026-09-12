from __future__ import annotations

import argparse
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from veritas.extraction_postverification_archive_receipt import (
    verify_postverification_external_archive_receipt_binding,
)
from veritas.extraction_postverification_archive_receipt_json import (
    load_extraction_postverification_external_archive_receipt,
    verified_postverification_external_archive_receipt_binding_json_payload,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HANDOFF_STATUS = (
    "repository_side_postverification_external_archive_handoff_ready_"
    "awaiting_independent_archive"
)
_ARCHIVE_OBJECT_KEYS = frozenset(
    {"archive_name", "source_path", "sha256", "size_bytes"}
)
_BOUND_VERIFICATION_ARCHIVE_NAME = "verification/bound-cold-verification.json"


def _file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"archive receipt input must be a regular non-symlink file: {path}")
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


def _load_handoff(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("post-verification external archive handoff must be UTF-8 JSON") from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "post-verification external archive handoff must contain valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise TypeError("post-verification external archive handoff root must be an object")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise TypeError(
            "post-verification external archive handoff schema_version must be an integer"
        )
    if schema_version != 1:
        raise ValueError(
            "post-verification external archive handoff schema_version must be 1"
        )
    if payload.get("status") != _HANDOFF_STATUS:
        raise ValueError(
            "post-verification external archive handoff is not awaiting independent archive"
        )
    if payload.get("production_authorized") is not False:
        raise ValueError(
            "post-verification external archive handoff must remain non-production"
        )
    pending = payload.get("pending_external_evidence")
    if not isinstance(pending, dict):
        raise TypeError(
            "post-verification external archive handoff pending_external_evidence must be an object"
        )
    for key in (
        "independent_archive_receipt_present",
        "independent_control_established",
        "historical_channel_semantics_established",
    ):
        if pending.get(key) is not False:
            raise ValueError(
                "repository-side post-verification handoff must not claim external authority: "
                f"{key}"
            )
    return payload


def _require_safe_archive_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("archive object archive_name must be a non-empty string")
    if value.startswith("/") or "\\" in value:
        raise ValueError("archive object archive_name must be a safe POSIX relative path")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("archive object archive_name must be a safe POSIX relative path")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_git_sha(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase 40-character git SHA")
    return value


def _rebuild_archive_object_set(handoff: dict[str, Any]) -> tuple[str, str]:
    objects = handoff.get("archive_objects")
    if not isinstance(objects, list) or not objects:
        raise ValueError(
            "post-verification external archive handoff must contain archive_objects"
        )

    stable_rows: list[dict[str, object]] = []
    seen_names: set[str] = set()
    bound_verification_sha256: str | None = None
    for index, row in enumerate(objects):
        if not isinstance(row, dict):
            raise TypeError(f"archive object {index} must be an object")
        actual_keys = frozenset(row)
        if actual_keys != _ARCHIVE_OBJECT_KEYS:
            missing = tuple(sorted(_ARCHIVE_OBJECT_KEYS - actual_keys))
            unknown = tuple(sorted(actual_keys - _ARCHIVE_OBJECT_KEYS))
            raise ValueError(
                "archive object keys differ from schema; "
                f"missing={missing!r}, unknown={unknown!r}"
            )
        archive_name = _require_safe_archive_name(row["archive_name"])
        if archive_name in seen_names:
            raise ValueError(f"duplicate archive object archive_name: {archive_name!r}")
        seen_names.add(archive_name)
        digest = _require_sha256(row["sha256"], label=f"archive object {archive_name} sha256")
        size_bytes = row["size_bytes"]
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
            raise TypeError(f"archive object {archive_name} size_bytes must be an integer")
        if size_bytes < 0:
            raise ValueError(f"archive object {archive_name} size_bytes must be non-negative")
        source_path = row["source_path"]
        if not isinstance(source_path, str) or not source_path:
            raise ValueError(f"archive object {archive_name} source_path must be non-empty")
        stable_rows.append(
            {
                "archive_name": archive_name,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
        )
        if archive_name == _BOUND_VERIFICATION_ARCHIVE_NAME:
            bound_verification_sha256 = digest

    if bound_verification_sha256 is None:
        raise ValueError(
            "post-verification archive object set is missing bound cold-verification bytes"
        )
    stable_rows.sort(key=lambda row: str(row["archive_name"]))
    raw = json.dumps(
        stable_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    object_set_sha256 = sha256(raw).hexdigest()

    claimed_object_set_sha256 = _require_sha256(
        handoff.get("archive_object_set_sha256"),
        label="handoff archive_object_set_sha256",
    )
    if claimed_object_set_sha256 != object_set_sha256:
        raise ValueError(
            "post-verification external archive handoff object-set SHA-256 does not reconstruct"
        )

    bound = handoff.get("bound_verification")
    if not isinstance(bound, dict):
        raise TypeError(
            "post-verification external archive handoff bound_verification must be an object"
        )
    claimed_bound_sha256 = _require_sha256(
        bound.get("file_sha256"),
        label="handoff bound verification file_sha256",
    )
    if claimed_bound_sha256 != bound_verification_sha256:
        raise ValueError(
            "post-verification handoff bound-verification witness differs from archive object set"
        )
    return object_set_sha256, bound_verification_sha256


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that an externally supplied post-verification archive receipt binds the exact "
            "repository handoff, reconstructed archive object set, bound cold-verification bytes, "
            "and independently selected custodian/channel/record context. Binding verification "
            "does not establish independent control or historical-channel semantics."
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
        raise SystemExit(
            "post-verification handoff bytes differ from independently expected SHA-256"
        )

    handoff = _load_handoff(args.handoff)
    source_commit_sha = _require_git_sha(
        handoff.get("source_commit_sha"),
        label="handoff source_commit_sha",
    )
    if source_commit_sha != args.expected_source_commit_sha:
        raise SystemExit(
            "post-verification handoff source commit differs from independently expected commit"
        )

    object_set_sha256, bound_verification_file_sha256 = _rebuild_archive_object_set(
        handoff
    )
    receipt_file_sha256 = _file_sha256(args.receipt)
    receipt = load_extraction_postverification_external_archive_receipt(args.receipt)
    verified = verify_postverification_external_archive_receipt_binding(
        receipt=receipt,
        receipt_file_sha256=receipt_file_sha256,
        expected_handoff_sha256=args.expected_handoff_sha256,
        expected_archived_object_set_sha256=object_set_sha256,
        expected_source_commit_sha=args.expected_source_commit_sha,
        expected_bound_verification_file_sha256=bound_verification_file_sha256,
        expected_custodian_identity=args.expected_custodian_identity,
        expected_archive_channel_identity=args.expected_archive_channel_identity,
        expected_archive_record_id=args.expected_archive_record_id,
    )
    payload = verified_postverification_external_archive_receipt_binding_json_payload(
        verified
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
