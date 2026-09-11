from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from test_extraction_calibration_archive_cli import _calibration_fixture
from test_extraction_execution_evidence import _execution_plan

from veritas.benchmark import BenchmarkSplit
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_execution_evidence import build_extraction_execution_evidence
from veritas.extraction_execution_evidence_json import (
    extraction_execution_attestation_json_payload,
)
from veritas.extraction_pretest_archive_receipt import (
    ExtractionPretestExternalArchiveReceipt,
    VerifiedPretestExternalArchiveReceiptBinding,
    extraction_pretest_archive_object_set_sha256,
)
from veritas.extraction_pretest_archive_receipt_json import (
    extraction_pretest_external_archive_receipt_json_payload,
    verified_pretest_external_archive_receipt_binding_json_payload,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _prepare(tmp_path: Path):
    fixture = _calibration_fixture(tmp_path)
    subprocess.run(
        fixture["freeze_args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    lock_path = tmp_path / "test-evaluation-lock.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_test_evaluation_lock.py",
            "--development-freeze",
            str(fixture["freeze_path"]),
            "--development-manifest",
            str(fixture["development_manifest_path"]),
            "--test-manifest",
            str(fixture["test_manifest_path"]),
            "--output",
            str(lock_path),
        ],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    source_commit_sha = "a" * 40
    initial_binding = VerifiedPretestExternalArchiveReceiptBinding(
        receipt_sha256="1" * 64,
        receipt_file_sha256="2" * 64,
        handoff_sha256="3" * 64,
        archived_object_set_sha256="4" * 64,
        source_commit_sha=source_commit_sha,
        pretest_witness_sha256="5" * 64,
        custodian_identity="independent-initial-custodian",
        archive_channel_identity="independent-initial-channel",
        archive_record_id="initial-record-001",
        external_timestamp_utc=None,
        external_sequence_position="initial-sequence-001",
    )
    initial_binding_path = tmp_path / "initial-archive-binding.json"
    _write_json(
        initial_binding_path,
        verified_pretest_external_archive_receipt_binding_json_payload(initial_binding),
    )

    development_manifest = load_extraction_split_target_manifest(
        fixture["development_manifest_path"]
    )
    execution_evidence = build_extraction_execution_evidence(
        plan=_execution_plan(),
        execution_id="development-nc-010",
        split=BenchmarkSplit.DEVELOPMENT,
        threshold_id="nc-010",
        threshold=0.01,
        target_manifest_sha256=development_manifest.sha256(),
        predictions=fixture["predictions"],
        prediction_artifact=fixture["prediction_path"].read_bytes(),
    )
    attestation_path = tmp_path / "development-nc-010.attestation.json"
    _write_json(
        attestation_path,
        extraction_execution_attestation_json_payload(execution_evidence.attestation),
    )

    handoff_path = tmp_path / "development-freeze-handoff.json"
    handoff_args = [
        sys.executable,
        "scripts/build_extraction_development_freeze_external_handoff.py",
        "--source-commit-sha",
        source_commit_sha,
        "--initial-archive-binding",
        str(initial_binding_path),
        "--pilot-threshold-policy",
        str(fixture["policy_path"]),
        "--development-freeze",
        str(fixture["freeze_path"]),
        "--development-manifest",
        str(fixture["development_manifest_path"]),
        "--test-evaluation-lock",
        str(lock_path),
        "--test-manifest",
        str(fixture["test_manifest_path"]),
        "--development-prediction",
        "nc-010",
        str(fixture["prediction_path"]),
        "--development-attestation",
        "nc-010",
        str(attestation_path),
        "--output",
        str(handoff_path),
    ]
    return fixture, lock_path, initial_binding, attestation_path, handoff_path, handoff_args


def test_post_development_handoff_reuses_existing_external_receipt_verifier(
    tmp_path: Path,
) -> None:
    (
        fixture,
        lock_path,
        initial_binding,
        attestation_path,
        handoff_path,
        handoff_args,
    ) = _prepare(tmp_path)

    result = subprocess.run(
        handoff_args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    handoff_file_sha256 = result.stdout.strip()
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))

    assert handoff_file_sha256 == hashlib.sha256(handoff_path.read_bytes()).hexdigest()
    assert handoff["production_authorized"] is False
    assert handoff["executed_v015_development_predictions"] is True
    assert handoff["executed_v015_test_predictions"] is False
    assert handoff["pretest_witness"]["sha256"] == hashlib.sha256(
        lock_path.read_bytes()
    ).hexdigest()
    assert handoff["previous_pretest_archive_binding"]["binding_sha256"] == (
        initial_binding.sha256()
    )
    assert handoff["development_executions"][0]["prediction_artifact_sha256"] == (
        hashlib.sha256(fixture["prediction_path"].read_bytes()).hexdigest()
    )
    assert handoff["development_executions"][0]["attestation_file_sha256"] == (
        hashlib.sha256(attestation_path.read_bytes()).hexdigest()
    )

    object_set_sha256 = extraction_pretest_archive_object_set_sha256(handoff)
    receipt = ExtractionPretestExternalArchiveReceipt(
        handoff_sha256=handoff_file_sha256,
        archived_object_set_sha256=object_set_sha256,
        source_commit_sha="a" * 40,
        pretest_witness_sha256=handoff["pretest_witness"]["sha256"],
        custodian_identity="independent-post-development-custodian",
        archive_channel_identity="independent-post-development-channel",
        archive_record_id="post-development-record-001",
        external_timestamp_utc=None,
        external_sequence_position="post-development-pre-test-001",
    )
    receipt_path = tmp_path / "post-development-receipt.json"
    _write_json(
        receipt_path,
        extraction_pretest_external_archive_receipt_json_payload(receipt),
    )
    verified_path = tmp_path / "post-development-verified-binding.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/verify_extraction_pretest_external_archive_receipt.py",
            "--receipt",
            str(receipt_path),
            "--handoff",
            str(handoff_path),
            "--expected-handoff-sha256",
            handoff_file_sha256,
            "--expected-source-commit-sha",
            "a" * 40,
            "--expected-custodian-identity",
            "independent-post-development-custodian",
            "--expected-archive-channel-identity",
            "independent-post-development-channel",
            "--expected-archive-record-id",
            "post-development-record-001",
            "--output",
            str(verified_path),
        ],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    verified = json.loads(verified_path.read_text(encoding="utf-8"))

    assert verified["handoff_sha256"] == handoff_file_sha256
    assert verified["archived_object_set_sha256"] == object_set_sha256
    assert verified["receipt_file_sha256"] == hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()
    assert verified["independent_control_established"] is False
    assert verified["historical_channel_semantics_established"] is False
    assert verified["production_authorized"] is False


def test_post_development_handoff_rejects_attestation_prediction_hash_drift(
    tmp_path: Path,
) -> None:
    fixture, _, _, attestation_path, handoff_path, handoff_args = _prepare(tmp_path)
    payload = json.loads(attestation_path.read_text(encoding="utf-8"))
    payload["prediction_artifact_sha256"] = "f" * 64
    _write_json(attestation_path, payload)

    result = subprocess.run(
        handoff_args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "attestation prediction bytes differ" in result.stderr
    assert not handoff_path.exists()
    assert hashlib.sha256(fixture["prediction_path"].read_bytes()).hexdigest() != "f" * 64


def test_post_development_handoff_rejects_initial_source_commit_drift(
    tmp_path: Path,
) -> None:
    _, _, _, _, handoff_path, handoff_args = _prepare(tmp_path)
    args = list(handoff_args)
    args[args.index("--source-commit-sha") + 1] = "b" * 40

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "initial archive binding is bound to a different source commit" in result.stderr
    assert not handoff_path.exists()
