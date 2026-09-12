from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ._strict_json import load_strict_json_object, require_exact_object_keys
from .extraction_pretest_archive_receipt import (
    ExtractionPretestExternalArchiveReceipt,
    VerifiedPretestExternalArchiveReceiptBinding,
)

_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "handoff_sha256",
        "archived_object_set_sha256",
        "source_commit_sha",
        "pretest_witness_sha256",
        "custodian_identity",
        "archive_channel_identity",
        "archive_record_id",
        "external_timestamp_utc",
        "external_sequence_position",
        "production_authorized",
    }
)


def load_extraction_pretest_external_archive_receipt(
    path: str | Path,
) -> ExtractionPretestExternalArchiveReceipt:
    payload = load_strict_json_object(path, label="pre-TEST external archive receipt")
    require_exact_object_keys(
        payload,
        _RECEIPT_KEYS,
        label="pre-TEST external archive receipt",
    )
    return ExtractionPretestExternalArchiveReceipt(
        handoff_sha256=payload["handoff_sha256"],
        archived_object_set_sha256=payload["archived_object_set_sha256"],
        source_commit_sha=payload["source_commit_sha"],
        pretest_witness_sha256=payload["pretest_witness_sha256"],
        custodian_identity=payload["custodian_identity"],
        archive_channel_identity=payload["archive_channel_identity"],
        archive_record_id=payload["archive_record_id"],
        external_timestamp_utc=payload["external_timestamp_utc"],
        external_sequence_position=payload["external_sequence_position"],
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def extraction_pretest_external_archive_receipt_json_payload(
    receipt: ExtractionPretestExternalArchiveReceipt,
) -> dict[str, Any]:
    if not isinstance(receipt, ExtractionPretestExternalArchiveReceipt):
        raise TypeError("receipt must be an ExtractionPretestExternalArchiveReceipt")
    return asdict(receipt)


def verified_pretest_external_archive_receipt_binding_json_payload(
    receipt: VerifiedPretestExternalArchiveReceiptBinding,
) -> dict[str, Any]:
    if not isinstance(receipt, VerifiedPretestExternalArchiveReceiptBinding):
        raise TypeError("receipt must be a VerifiedPretestExternalArchiveReceiptBinding")
    return asdict(receipt)
