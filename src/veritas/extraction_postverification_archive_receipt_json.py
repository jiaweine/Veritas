from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .extraction_postverification_archive_receipt import (
    ExtractionPostverificationExternalArchiveReceipt,
    VerifiedPostverificationExternalArchiveReceiptBinding,
)

_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "handoff_sha256",
        "archived_object_set_sha256",
        "source_commit_sha",
        "bound_verification_file_sha256",
        "custodian_identity",
        "archive_channel_identity",
        "archive_record_id",
        "external_timestamp_utc",
        "external_sequence_position",
        "production_authorized",
    }
)


def load_extraction_postverification_external_archive_receipt(
    path: str | Path,
) -> ExtractionPostverificationExternalArchiveReceipt:
    payload = _load_strict_json_file(
        path,
        label="post-verification external archive receipt",
    )
    _require_exact_object_keys(
        payload,
        _RECEIPT_KEYS,
        label="post-verification external archive receipt",
    )
    return ExtractionPostverificationExternalArchiveReceipt(
        handoff_sha256=payload["handoff_sha256"],
        archived_object_set_sha256=payload["archived_object_set_sha256"],
        source_commit_sha=payload["source_commit_sha"],
        bound_verification_file_sha256=payload["bound_verification_file_sha256"],
        custodian_identity=payload["custodian_identity"],
        archive_channel_identity=payload["archive_channel_identity"],
        archive_record_id=payload["archive_record_id"],
        external_timestamp_utc=payload["external_timestamp_utc"],
        external_sequence_position=payload["external_sequence_position"],
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def extraction_postverification_external_archive_receipt_json_payload(
    receipt: ExtractionPostverificationExternalArchiveReceipt,
) -> dict[str, Any]:
    if not isinstance(receipt, ExtractionPostverificationExternalArchiveReceipt):
        raise TypeError(
            "receipt must be an ExtractionPostverificationExternalArchiveReceipt"
        )
    return asdict(receipt)


def verified_postverification_external_archive_receipt_binding_json_payload(
    binding: VerifiedPostverificationExternalArchiveReceiptBinding,
) -> dict[str, Any]:
    if not isinstance(binding, VerifiedPostverificationExternalArchiveReceiptBinding):
        raise TypeError(
            "binding must be a VerifiedPostverificationExternalArchiveReceiptBinding"
        )
    return asdict(binding)


def _load_strict_json_file(path: str | Path, *, label: str) -> dict[str, Any]:
    source_path = Path(path)
    raw = source_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{label} root must be an object")
    return payload


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key is not allowed: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")


def _require_exact_object_keys(
    value: object,
    expected: frozenset[str],
    *,
    label: str,
) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        unknown = tuple(sorted(actual - expected))
        raise ValueError(
            f"{label} keys differ from schema; missing={missing!r}, unknown={unknown!r}"
        )
