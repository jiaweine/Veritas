from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ._strict_json import load_strict_json_object, require_exact_object_keys
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
    payload = load_strict_json_object(
        path,
        label="post-verification external archive receipt",
    )
    require_exact_object_keys(
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
