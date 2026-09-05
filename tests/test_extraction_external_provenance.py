from __future__ import annotations

from dataclasses import replace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_extraction_execution_evidence import _attested_release, _execution_plan

from veritas.extraction_external_provenance import (
    ExtractionExternalTrustRoot,
    ExtractionSignedExternalProvenance,
    build_extraction_external_provenance_statement,
    extraction_external_provenance_statement_bytes,
    verify_external_extraction_provenance,
)

_COMMIT_SHA = "a" * 40


def _keypair():
    private_key = Ed25519PrivateKey.generate()
    public_key_hex = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    return private_key, public_key_hex


def _trust_root(public_key_hex: str) -> ExtractionExternalTrustRoot:
    return ExtractionExternalTrustRoot(
        issuer="github-actions",
        runner_identity="github-hosted:ubuntu-latest",
        repository="jiaweine/Veritas",
        workflow_identity=".github/workflows/ci.yml",
        public_key_hex=public_key_hex,
    )


def _signed_fixture():
    private_key, public_key_hex = _keypair()
    trust_root = _trust_root(public_key_hex)
    execution_plan = _execution_plan()
    attested_release = _attested_release(execution_plan=execution_plan)
    statement = build_extraction_external_provenance_statement(
        trust_root=trust_root,
        run_id="33906297424",
        run_attempt=1,
        commit_sha=_COMMIT_SHA,
        attested_release_receipt=attested_release,
        execution_plan=execution_plan,
    )
    signature_hex = private_key.sign(
        extraction_external_provenance_statement_bytes(statement)
    ).hex()
    signed = ExtractionSignedExternalProvenance(
        statement=statement,
        signature_hex=signature_hex,
    )
    return trust_root, execution_plan, attested_release, signed


def test_valid_external_signature_produces_nonproduction_verified_receipt() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()

    receipt = verify_external_extraction_provenance(
        trust_root=trust_root,
        signed_provenance=signed,
        attested_release_receipt=attested_release,
        execution_plan=execution_plan,
    )

    assert receipt.production_authorized is False
    assert receipt.attested_release_receipt_sha256 == attested_release.sha256()
    assert receipt.execution_plan_sha256 == execution_plan.sha256()
    assert receipt.trust_root_sha256 == trust_root.sha256()
    assert receipt.provenance_statement_sha256 == signed.statement.sha256()
    assert receipt.provenance_envelope_sha256 == signed.sha256()
    assert len(receipt.sha256()) == 64


def test_wrong_public_key_rejects_valid_statement_signature() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    _, other_public_key_hex = _keypair()
    wrong_root = replace(trust_root, public_key_hex=other_public_key_hex)
    rebound_statement = replace(signed.statement, trust_root_sha256=wrong_root.sha256())
    rebound_signed = replace(signed, statement=rebound_statement)

    with pytest.raises(ValueError, match="signature is invalid"):
        verify_external_extraction_provenance(
            trust_root=wrong_root,
            signed_provenance=rebound_signed,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
        )


def test_signature_cannot_be_replayed_after_run_id_tampering() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    tampered = replace(signed, statement=replace(signed.statement, run_id="different-run"))

    with pytest.raises(ValueError, match="signature is invalid"):
        verify_external_extraction_provenance(
            trust_root=trust_root,
            signed_provenance=tampered,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
        )


def test_signed_subject_must_match_exact_attested_release_receipt() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    forged_statement = replace(
        signed.statement,
        attested_release_receipt_sha256="f" * 64,
    )
    forged = replace(signed, statement=forged_statement)

    with pytest.raises(ValueError, match="subject or trusted runner identity"):
        verify_external_extraction_provenance(
            trust_root=trust_root,
            signed_provenance=forged,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
        )


def test_execution_plan_drift_breaks_external_provenance_binding() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    changed_plan = replace(execution_plan, source_tree_sha256="9" * 64)

    with pytest.raises(ValueError, match="different execution plan"):
        verify_external_extraction_provenance(
            trust_root=trust_root,
            signed_provenance=signed,
            attested_release_receipt=attested_release,
            execution_plan=changed_plan,
        )


def test_external_provenance_types_fail_closed() -> None:
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    with pytest.raises(ValueError, match="64-byte lowercase Ed25519 signature"):
        replace(signed, signature_hex="00")
    with pytest.raises(ValueError, match="40-character git SHA"):
        replace(signed.statement, commit_sha="not-a-git-sha")
    with pytest.raises(TypeError, match="run_attempt"):
        replace(signed.statement, run_attempt=True)
    with pytest.raises(ValueError, match="non-production"):
        receipt = verify_external_extraction_provenance(
            trust_root=trust_root,
            signed_provenance=signed,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
        )
        replace(receipt, production_authorized=True)
