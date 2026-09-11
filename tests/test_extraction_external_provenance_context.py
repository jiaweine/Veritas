from __future__ import annotations

from dataclasses import replace

import pytest
from test_extraction_external_provenance import _signed_fixture

from veritas.extraction_external_provenance_context import (
    verify_external_extraction_provenance_for_run,
)


def test_run_context_verifier_records_exact_verified_run_identity() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    receipt = verify_external_extraction_provenance_for_run(
        trust_root=trust_root,
        signed_provenance=signed,
        attested_release_receipt=attested_release,
        execution_plan=execution_plan,
        expected_run_id=signed.statement.run_id,
        expected_run_attempt=signed.statement.run_attempt,
        expected_commit_sha=signed.statement.commit_sha,
    )

    assert receipt.production_authorized is False
    assert receipt.run_id == signed.statement.run_id
    assert receipt.run_attempt == signed.statement.run_attempt
    assert receipt.commit_sha == signed.statement.commit_sha
    assert receipt.repository == trust_root.repository
    assert receipt.workflow_identity == trust_root.workflow_identity
    assert receipt.runner_identity == trust_root.runner_identity
    assert len(receipt.verified_evidence_receipt_sha256) == 64
    assert len(receipt.sha256()) == 64


def test_valid_signature_for_other_run_id_cannot_satisfy_expected_context() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    with pytest.raises(ValueError, match="run_id differs"):
        verify_external_extraction_provenance_for_run(
            trust_root=trust_root,
            signed_provenance=signed,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
            expected_run_id="different-run",
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha=signed.statement.commit_sha,
        )


def test_valid_signature_for_other_run_attempt_cannot_satisfy_expected_context() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    with pytest.raises(ValueError, match="run_attempt differs"):
        verify_external_extraction_provenance_for_run(
            trust_root=trust_root,
            signed_provenance=signed,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=2,
            expected_commit_sha=signed.statement.commit_sha,
        )


def test_valid_signature_for_other_commit_cannot_satisfy_expected_context() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    with pytest.raises(ValueError, match="commit_sha differs"):
        verify_external_extraction_provenance_for_run(
            trust_root=trust_root,
            signed_provenance=signed,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha="b" * 40,
        )


def test_run_context_types_and_authority_fail_closed() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    with pytest.raises(TypeError, match="run attempt"):
        verify_external_extraction_provenance_for_run(
            trust_root=trust_root,
            signed_provenance=signed,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=True,
            expected_commit_sha=signed.statement.commit_sha,
        )

    receipt = verify_external_extraction_provenance_for_run(
        trust_root=trust_root,
        signed_provenance=signed,
        attested_release_receipt=attested_release,
        execution_plan=execution_plan,
        expected_run_id=signed.statement.run_id,
        expected_run_attempt=signed.statement.run_attempt,
        expected_commit_sha=signed.statement.commit_sha,
    )
    with pytest.raises(ValueError, match="non-production"):
        replace(receipt, production_authorized=True)
