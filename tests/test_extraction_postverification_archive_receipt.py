from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from test_extraction_external_provenance_cli import _root
from test_extraction_postverification_external_handoff import _run_bound_then_handoff

from veritas.extraction_postverification_archive_receipt import (
    ExtractionPostverificationExternalArchiveReceipt,
    verify_postverification_external_archive_receipt_binding,
)
from veritas.extraction_postverification_archive_receipt_json import (
    extraction_postverification_external_archive_receipt_json_payload,
    load_extraction_postverification_external_archive_receipt,
)

_CUSTODIAN = "independent-postverification-custodian-example"
_CHANNEL = "append-only-postverification-channel-example"
_RECORD = "postverification-record-example-001"


def _build_handoff(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    _, args, handoff_path = _run_bound_then_handoff(tmp_path)
    completed = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return handoff_path, json.loads(handoff_path.read_text(encoding="utf-8"))


def _receipt(handoff_path: Path, handoff: dict[str, object]):
    bound = handoff["bound_verification"]
    assert isinstance(bound, dict)
    return ExtractionPostverificationExternalArchiveReceipt(
        handoff_sha256=hashlib.sha256(handoff_path.read_bytes()).hexdigest(),
        archived_object_set_sha256=str(handoff["archive_object_set_sha256"]),
        source_commit_sha=str(handoff["source_commit_sha"]),
        bound_verification_file_sha256=str(bound["file_sha256"]),
        custodian_identity=_CUSTODIAN,
        archive_channel_identity=_CHANNEL,
        archive_record_id=_RECORD,
        external_timestamp_utc="2026-09-12T08:30:00Z",
        external_sequence_position="postverification-sequence-example-001",
    )


def _write_receipt(path: Path, receipt: ExtractionPostverificationExternalArchiveReceipt) -> None:
    path.write_text(
        json.dumps(
            extraction_postverification_external_archive_receipt_json_payload(receipt),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _verify_command(
    *,
    receipt_path: Path,
    handoff_path: Path,
    receipt: ExtractionPostverificationExternalArchiveReceipt,
    output_path: Path,
) -> list[str]:
    return [
        sys.executable,
        "scripts/verify_extraction_postverification_external_archive_receipt.py",
        "--receipt",
        str(receipt_path),
        "--handoff",
        str(handoff_path),
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


def test_postverification_receipt_binding_preserves_non_authority_boundary(
    tmp_path: Path,
) -> None:
    handoff_path, handoff = _build_handoff(tmp_path)
    receipt = _receipt(handoff_path, handoff)
    verified = verify_postverification_external_archive_receipt_binding(
        receipt=receipt,
        receipt_file_sha256="0" * 64,
        expected_handoff_sha256=receipt.handoff_sha256,
        expected_archived_object_set_sha256=receipt.archived_object_set_sha256,
        expected_source_commit_sha=receipt.source_commit_sha,
        expected_bound_verification_file_sha256=receipt.bound_verification_file_sha256,
        expected_custodian_identity=receipt.custodian_identity,
        expected_archive_channel_identity=receipt.archive_channel_identity,
        expected_archive_record_id=receipt.archive_record_id,
    )

    assert verified.receipt_sha256 == receipt.sha256()
    assert verified.independent_control_established is False
    assert verified.historical_channel_semantics_established is False
    assert verified.production_authorized is False

    with pytest.raises(ValueError, match="must remain false"):
        replace(verified, independent_control_established=True)
    with pytest.raises(ValueError, match="must remain false"):
        replace(verified, historical_channel_semantics_established=True)
    with pytest.raises(ValueError, match="must remain false"):
        replace(verified, production_authorized=True)


def test_postverification_receipt_requires_external_time_or_sequence(tmp_path: Path) -> None:
    handoff_path, handoff = _build_handoff(tmp_path)
    with pytest.raises(ValueError, match="timestamp or sequence"):
        replace(
            _receipt(handoff_path, handoff),
            external_timestamp_utc=None,
            external_sequence_position=None,
        )


def test_postverification_receipt_strict_loader_rejects_unknown_and_duplicate_keys(
    tmp_path: Path,
) -> None:
    handoff_path, handoff = _build_handoff(tmp_path)
    receipt = _receipt(handoff_path, handoff)
    payload = extraction_postverification_external_archive_receipt_json_payload(receipt)

    unknown = dict(payload)
    unknown["claims_independent_control"] = True
    unknown_path = tmp_path / "unknown-receipt.json"
    unknown_path.write_text(json.dumps(unknown), encoding="utf-8")
    with pytest.raises(ValueError, match="keys differ from schema"):
        load_extraction_postverification_external_archive_receipt(unknown_path)

    duplicate_path = tmp_path / "duplicate-receipt.json"
    rendered = json.dumps(payload, sort_keys=True)
    duplicate_path.write_text(
        rendered[:-1] + ',"handoff_sha256":"' + receipt.handoff_sha256 + '"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate object key"):
        load_extraction_postverification_external_archive_receipt(duplicate_path)


def test_postverification_receipt_cli_verifies_independently_supplied_context(
    tmp_path: Path,
) -> None:
    handoff_path, handoff = _build_handoff(tmp_path)
    receipt = _receipt(handoff_path, handoff)
    receipt_path = tmp_path / "external-receipt.json"
    output_path = tmp_path / "verified-postverification-receipt-binding.json"
    _write_receipt(receipt_path, receipt)

    command = _verify_command(
        receipt_path=receipt_path,
        handoff_path=handoff_path,
        receipt=receipt,
        output_path=output_path,
    )
    completed = subprocess.run(
        command,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["handoff_sha256"] == receipt.handoff_sha256
    assert payload["archived_object_set_sha256"] == receipt.archived_object_set_sha256
    assert payload["bound_verification_file_sha256"] == (
        receipt.bound_verification_file_sha256
    )
    assert payload["receipt_file_sha256"] == hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()
    assert payload["independent_control_established"] is False
    assert payload["historical_channel_semantics_established"] is False
    assert payload["production_authorized"] is False

    drifted = command.copy()
    index = drifted.index("--expected-archive-record-id") + 1
    drifted[index] = "different-postverification-record"
    rejected = subprocess.run(
        drifted,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "different archive record id" in rejected.stderr


def test_postverification_receipt_cli_rejects_handoff_exact_byte_drift(
    tmp_path: Path,
) -> None:
    handoff_path, handoff = _build_handoff(tmp_path)
    receipt = _receipt(handoff_path, handoff)
    receipt_path = tmp_path / "external-receipt.json"
    output_path = tmp_path / "verified.json"
    _write_receipt(receipt_path, receipt)

    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        _verify_command(
            receipt_path=receipt_path,
            handoff_path=handoff_path,
            receipt=receipt,
            output_path=output_path,
        ),
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "handoff bytes differ from independently expected SHA-256" in completed.stderr
    assert not output_path.exists()


def test_postverification_receipt_cli_rebuilds_object_set_instead_of_trusting_claim(
    tmp_path: Path,
) -> None:
    handoff_path, handoff = _build_handoff(tmp_path)
    objects = handoff["archive_objects"]
    assert isinstance(objects, list)
    assert isinstance(objects[0], dict)
    objects[0]["sha256"] = "f" * 64
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    receipt = _receipt(handoff_path, handoff)
    receipt_path = tmp_path / "external-receipt.json"
    output_path = tmp_path / "verified.json"
    _write_receipt(receipt_path, receipt)

    completed = subprocess.run(
        _verify_command(
            receipt_path=receipt_path,
            handoff_path=handoff_path,
            receipt=receipt,
            output_path=output_path,
        ),
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "object-set SHA-256 does not reconstruct" in completed.stderr
    assert not output_path.exists()


def test_postverification_receipt_cli_rejects_bound_verification_witness_drift(
    tmp_path: Path,
) -> None:
    handoff_path, handoff = _build_handoff(tmp_path)
    receipt = _receipt(handoff_path, handoff)
    receipt = replace(receipt, bound_verification_file_sha256="f" * 64)
    receipt_path = tmp_path / "external-receipt.json"
    output_path = tmp_path / "verified.json"
    _write_receipt(receipt_path, receipt)

    completed = subprocess.run(
        _verify_command(
            receipt_path=receipt_path,
            handoff_path=handoff_path,
            receipt=receipt,
            output_path=output_path,
        ),
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "different bound verification bytes" in completed.stderr
    assert not output_path.exists()
