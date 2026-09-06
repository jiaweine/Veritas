from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path

from test_extraction_external_provenance import _keypair, _trust_root
from test_extraction_external_provenance_cli import _archived_fixture, _root, _write_json

from veritas.extraction_execution_evidence_json import load_extraction_execution_plan
from veritas.extraction_external_provenance_json import extraction_external_trust_root_payload
from veritas.extraction_source_archive_provenance import (
    ExtractionSignedSourceArchiveProvenance,
    build_extraction_source_archive_provenance_statement,
    build_extraction_source_archive_trust_policy,
    extraction_source_archive_provenance_statement_bytes,
)
from veritas.extraction_source_archive_provenance_json import (
    extraction_signed_source_archive_provenance_json_payload,
    extraction_source_archive_trust_policy_json_payload,
)


def _add_source_archive_chain(tmp_path: Path, fixture: dict[str, object]) -> list[str]:
    args = list(fixture["args"])
    execution_plan_path = Path(args[args.index("--execution-plan") + 1])
    execution_plan = load_extraction_execution_plan(execution_plan_path)
    private_key, public_key_hex = _keypair()
    trust_root = _trust_root(public_key_hex)
    policy = build_extraction_source_archive_trust_policy(
        policy_id="trusted-source-archive-v1",
        execution_plan=execution_plan,
        source_commit_sha=str(fixture["commit_sha"]),
        trust_root=trust_root,
    )
    statement = build_extraction_source_archive_provenance_statement(
        trust_root=trust_root,
        run_id="source-archive-build-1",
        run_attempt=1,
        source_commit_sha=str(fixture["commit_sha"]),
        execution_plan=execution_plan,
    )
    signed = ExtractionSignedSourceArchiveProvenance(
        statement=statement,
        signature_hex=private_key.sign(
            extraction_source_archive_provenance_statement_bytes(statement)
        ).hex(),
    )

    root_path = tmp_path / "source-archive-trust-root.json"
    policy_path = tmp_path / "source-archive-trust-policy.json"
    signed_path = tmp_path / "signed-source-archive-provenance.json"
    _write_json(root_path, extraction_external_trust_root_payload(trust_root))
    _write_json(policy_path, extraction_source_archive_trust_policy_json_payload(policy))
    _write_json(
        signed_path,
        extraction_signed_source_archive_provenance_json_payload(signed),
    )

    output_index = args.index("--output")
    args[output_index:output_index] = [
        "--source-archive-trust-root",
        str(root_path),
        "--source-archive-trust-policy",
        str(policy_path),
        "--signed-source-archive-provenance",
        str(signed_path),
        "--expected-source-archive-run-id",
        statement.run_id,
        "--expected-source-archive-run-attempt",
        str(statement.run_attempt),
    ]
    return args


def test_cold_verifier_emits_source_archive_receipt_for_complete_trusted_chain(
    tmp_path: Path,
) -> None:
    fixture = _archived_fixture(tmp_path)
    args = _add_source_archive_chain(tmp_path, fixture)

    result = subprocess.run(
        args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(Path(fixture["output_path"]).read_text(encoding="utf-8"))
    source_receipt = payload["source_archive_receipt"]
    source_tree_bytes = fixture["artifacts"]["source_tree"].read_bytes()
    assert source_receipt["source_commit_sha"] == fixture["commit_sha"]
    assert source_receipt["source_tree_sha256"] == sha256(source_tree_bytes).hexdigest()
    assert source_receipt["production_authorized"] is False
    assert len(payload["source_archive_receipt_sha256"]) == 64
    assert result.stdout.strip() == payload["receipt_sha256"]


def test_cold_verifier_rejects_partial_source_archive_chain(tmp_path: Path) -> None:
    fixture = _archived_fixture(tmp_path)
    args = list(fixture["args"])
    output_index = args.index("--output")
    args[output_index:output_index] = [
        "--expected-source-archive-run-id",
        "source-archive-build-1",
    ]

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "source archive provenance verification requires" in result.stderr


def test_cold_verifier_rejects_wrong_independent_source_archive_run(tmp_path: Path) -> None:
    fixture = _archived_fixture(tmp_path)
    args = _add_source_archive_chain(tmp_path, fixture)
    run_index = args.index("source-archive-build-1")
    args[run_index] = "different-build-run"

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "run_id differs from expected build run" in result.stderr
