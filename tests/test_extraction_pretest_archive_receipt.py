from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from veritas.extraction_pretest_archive_receipt import (
    ExtractionPretestExternalArchiveReceipt,
    extraction_pretest_archive_object_set_sha256,
    verify_pretest_external_archive_receipt_binding,
)
from veritas.extraction_pretest_archive_receipt_json import (
    extraction_pretest_external_archive_receipt_json_payload,
    load_extraction_pretest_external_archive_receipt,
)

_HANDOFF_PATH = Path("benchmark/extraction/pretest_external_archive_handoff_v0.15.json")
_HANDOFF_FILE_SHA256 = "90fe5c7e27b7a8133fad0d5ce485b7f6866383fa6ddf3155403c098aa4acb7fa"
_MOCK_RECEIPT_FILE_SHA256 = "0" * 64


def _handoff() -> dict[str, object]:
    return json.loads(_HANDOFF_PATH.read_text(encoding="utf-8"))


def _receipt() -> ExtractionPretestExternalArchiveReceipt:
    handoff = _handoff()
    witness = handoff["pretest_witness"]
    assert isinstance(witness, dict)
    return ExtractionPretestExternalArchiveReceipt(
        handoff_sha256=_HANDOFF_FILE_SHA256,
        archived_object_set_sha256=extraction_pretest_archive_object_set_sha256(handoff),
        source_commit_sha=str(handoff["source_commit_sha"]),
        pretest_witness_sha256=str(witness["sha256"]),
        custodian_identity="independent-custodian-example",
        archive_channel_identity="append-only-channel-example",
        archive_record_id="record-example-001",
        external_timestamp_utc="2026-09-07T11:00:00Z",
        external_sequence_position="sequence-example-001",
    )


def test_frozen_handoff_file_hash_and_receipt_binding_contract() -> None:
    assert hashlib.sha256(_HANDOFF_PATH.read_bytes()).hexdigest() == _HANDOFF_FILE_SHA256
    receipt = _receipt()
    verified = verify_pretest_external_archive_receipt_binding(
        receipt=receipt,
        receipt_file_sha256=_MOCK_RECEIPT_FILE_SHA256,
        expected_handoff_sha256=receipt.handoff_sha256,
        expected_archived_object_set_sha256=receipt.archived_object_set_sha256,
        expected_source_commit_sha=receipt.source_commit_sha,
        expected_pretest_witness_sha256=receipt.pretest_witness_sha256,
        expected_custodian_identity=receipt.custodian_identity,
        expected_archive_channel_identity=receipt.archive_channel_identity,
        expected_archive_record_id=receipt.archive_record_id,
    )

    assert verified.receipt_sha256 == receipt.sha256()
    assert verified.receipt_file_sha256 == _MOCK_RECEIPT_FILE_SHA256
    assert verified.independent_control_established is False
    assert verified.historical_channel_semantics_established is False
    assert verified.production_authorized is False


def test_receipt_requires_external_timestamp_or_sequence_position() -> None:
    with pytest.raises(ValueError, match="timestamp or sequence"):
        replace(
            _receipt(),
            external_timestamp_utc=None,
            external_sequence_position=None,
        )


def test_receipt_rejects_non_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="ending in Z"):
        replace(_receipt(), external_timestamp_utc="2026-09-07T11:00:00+01:00")


def test_receipt_binding_rejects_posthoc_context_drift() -> None:
    receipt = _receipt()
    with pytest.raises(ValueError, match="different archive channel identity"):
        verify_pretest_external_archive_receipt_binding(
            receipt=receipt,
            receipt_file_sha256=_MOCK_RECEIPT_FILE_SHA256,
            expected_handoff_sha256=receipt.handoff_sha256,
            expected_archived_object_set_sha256=receipt.archived_object_set_sha256,
            expected_source_commit_sha=receipt.source_commit_sha,
            expected_pretest_witness_sha256=receipt.pretest_witness_sha256,
            expected_custodian_identity=receipt.custodian_identity,
            expected_archive_channel_identity="different-channel",
            expected_archive_record_id=receipt.archive_record_id,
        )


def test_object_set_hash_changes_when_archived_universe_changes() -> None:
    handoff = _handoff()
    baseline = extraction_pretest_archive_object_set_sha256(handoff)
    changed = json.loads(json.dumps(handoff))
    repository_files = changed["repository_files"]
    assert isinstance(repository_files, list)
    assert isinstance(repository_files[0], dict)
    repository_files[0]["sha256"] = "f" * 64
    assert extraction_pretest_archive_object_set_sha256(changed) != baseline


def test_strict_receipt_loader_rejects_unknown_and_duplicate_keys(tmp_path: Path) -> None:
    receipt = _receipt()
    payload = extraction_pretest_external_archive_receipt_json_payload(receipt)

    unknown = dict(payload)
    unknown["claims_independence"] = True
    unknown_path = tmp_path / "unknown.json"
    unknown_path.write_text(json.dumps(unknown), encoding="utf-8")
    with pytest.raises(ValueError, match="keys differ from schema"):
        load_extraction_pretest_external_archive_receipt(unknown_path)

    duplicate_path = tmp_path / "duplicate.json"
    rendered = json.dumps(payload, sort_keys=True)
    duplicate_path.write_text(
        rendered[:-1] + ',"handoff_sha256":"' + receipt.handoff_sha256 + '"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate object key"):
        load_extraction_pretest_external_archive_receipt(duplicate_path)


def test_receipt_semantic_hash_does_not_substitute_for_exact_file_identity(tmp_path: Path) -> None:
    payload = extraction_pretest_external_archive_receipt_json_payload(_receipt())
    compact_path = tmp_path / "receipt-compact.json"
    pretty_path = tmp_path / "receipt-pretty.json"
    compact_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    pretty_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    compact = load_extraction_pretest_external_archive_receipt(compact_path)
    pretty = load_extraction_pretest_external_archive_receipt(pretty_path)

    assert compact.sha256() == pretty.sha256()
    assert hashlib.sha256(compact_path.read_bytes()).hexdigest() != hashlib.sha256(
        pretty_path.read_bytes()
    ).hexdigest()


def test_receipt_and_verified_binding_cannot_authorize_production() -> None:
    receipt = _receipt()
    with pytest.raises(ValueError, match="non-production"):
        replace(receipt, production_authorized=True)

    verified = verify_pretest_external_archive_receipt_binding(
        receipt=receipt,
        receipt_file_sha256=_MOCK_RECEIPT_FILE_SHA256,
        expected_handoff_sha256=receipt.handoff_sha256,
        expected_archived_object_set_sha256=receipt.archived_object_set_sha256,
        expected_source_commit_sha=receipt.source_commit_sha,
        expected_pretest_witness_sha256=receipt.pretest_witness_sha256,
        expected_custodian_identity=receipt.custodian_identity,
        expected_archive_channel_identity=receipt.archive_channel_identity,
        expected_archive_record_id=receipt.archive_record_id,
    )
    with pytest.raises(ValueError, match="must remain false"):
        replace(verified, independent_control_established=True)
    with pytest.raises(ValueError, match="must remain false"):
        replace(verified, historical_channel_semantics_established=True)
    with pytest.raises(ValueError, match="must remain false"):
        replace(verified, production_authorized=True)


def test_cold_receipt_cli_requires_independently_supplied_context(tmp_path: Path) -> None:
    receipt = _receipt()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(
            extraction_pretest_external_archive_receipt_json_payload(receipt),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "verified.json"
    command = [
        sys.executable,
        "scripts/verify_extraction_pretest_external_archive_receipt.py",
        "--receipt",
        str(receipt_path),
        "--handoff",
        str(_HANDOFF_PATH),
        "--expected-handoff-sha256",
        receipt.handoff_sha256,
        "--expected-source-commit-sha",
        receipt.source_commit_sha,
        "--expected-custodian-identity",
        receipt.custodian_identity,
        "--expected-archive-channel-identity",
        receipt.archive_channel_identity,
        "--expected-archive-record-id",
        receipt.archive_record_id,
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    verified = json.loads(output_path.read_text(encoding="utf-8"))
    assert verified["receipt_file_sha256"] == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    assert verified["independent_control_established"] is False
    assert verified["historical_channel_semantics_established"] is False
    assert verified["production_authorized"] is False

    drifted = command.copy()
    record_index = drifted.index("--expected-archive-record-id") + 1
    drifted[record_index] = "different-record"
    rejected = subprocess.run(drifted, check=False, capture_output=True, text=True)
    assert rejected.returncode != 0
    assert "different archive record id" in rejected.stderr


def test_cold_receipt_cli_rejects_boolean_handoff_schema_version(tmp_path: Path) -> None:
    handoff = _handoff()
    handoff["schema_version"] = True
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    handoff_sha256 = hashlib.sha256(handoff_path.read_bytes()).hexdigest()

    receipt = replace(_receipt(), handoff_sha256=handoff_sha256)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(
            extraction_pretest_external_archive_receipt_json_payload(receipt),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    command = [
        sys.executable,
        "scripts/verify_extraction_pretest_external_archive_receipt.py",
        "--receipt",
        str(receipt_path),
        "--handoff",
        str(handoff_path),
        "--expected-handoff-sha256",
        handoff_sha256,
        "--expected-source-commit-sha",
        receipt.source_commit_sha,
        "--expected-custodian-identity",
        receipt.custodian_identity,
        "--expected-archive-channel-identity",
        receipt.archive_channel_identity,
        "--expected-archive-record-id",
        receipt.archive_record_id,
    ]
    rejected = subprocess.run(command, check=False, capture_output=True, text=True)
    assert rejected.returncode != 0
    assert "schema_version must be an integer" in rejected.stderr
