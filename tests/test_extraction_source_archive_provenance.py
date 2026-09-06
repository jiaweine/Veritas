from __future__ import annotations

from dataclasses import replace

import pytest
from test_extraction_execution_evidence import _execution_plan
from test_extraction_external_provenance import _keypair, _trust_root

from veritas.extraction_source_archive_provenance import (
    ExtractionSignedSourceArchiveProvenance,
    build_extraction_source_archive_provenance_statement,
    build_extraction_source_archive_trust_policy,
    extraction_source_archive_provenance_statement_bytes,
    verify_precommitted_extraction_source_archive_provenance_for_run,
)

_COMMIT_SHA = "a" * 40


def _source_archive_fixture():
    private_key, public_key_hex = _keypair()
    trust_root = _trust_root(public_key_hex)
    execution_plan = _execution_plan()
    policy = build_extraction_source_archive_trust_policy(
        policy_id="source-archive-v1",
        execution_plan=execution_plan,
        source_commit_sha=_COMMIT_SHA,
        trust_root=trust_root,
    )
    statement = build_extraction_source_archive_provenance_statement(
        trust_root=trust_root,
        run_id="source-archive-run-1",
        run_attempt=1,
        source_commit_sha=_COMMIT_SHA,
        execution_plan=execution_plan,
    )
    signed = ExtractionSignedSourceArchiveProvenance(
        statement=statement,
        signature_hex=private_key.sign(
            extraction_source_archive_provenance_statement_bytes(statement)
        ).hex(),
    )
    return policy, trust_root, execution_plan, signed


def test_precommitted_source_archive_provenance_binds_commit_to_archive() -> None:
    policy, trust_root, execution_plan, signed = _source_archive_fixture()

    receipt = verify_precommitted_extraction_source_archive_provenance_for_run(
        trust_policy=policy,
        trust_root=trust_root,
        signed_provenance=signed,
        execution_plan=execution_plan,
        expected_run_id=signed.statement.run_id,
        expected_run_attempt=signed.statement.run_attempt,
        expected_commit_sha=_COMMIT_SHA,
    )

    assert receipt.production_authorized is False
    assert receipt.trust_policy_sha256 == policy.sha256()
    assert receipt.trust_root_sha256 == trust_root.sha256()
    assert receipt.execution_plan_sha256 == execution_plan.sha256()
    assert receipt.source_commit_sha == _COMMIT_SHA
    assert receipt.source_tree_sha256 == execution_plan.source_tree_sha256
    assert receipt.provenance_statement_sha256 == signed.statement.sha256()
    assert receipt.provenance_envelope_sha256 == signed.sha256()
    assert receipt.run_id == signed.statement.run_id
    assert receipt.run_attempt == signed.statement.run_attempt
    assert len(receipt.sha256()) == 64


def test_source_archive_policy_rejects_posthoc_source_tree_drift() -> None:
    policy, trust_root, execution_plan, signed = _source_archive_fixture()
    changed_plan = replace(execution_plan, source_tree_sha256="9" * 64)

    with pytest.raises(ValueError, match="different execution plan"):
        verify_precommitted_extraction_source_archive_provenance_for_run(
            trust_policy=policy,
            trust_root=trust_root,
            signed_provenance=signed,
            execution_plan=changed_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha=_COMMIT_SHA,
        )


def test_source_archive_policy_rejects_posthoc_expected_commit_drift() -> None:
    policy, trust_root, execution_plan, signed = _source_archive_fixture()

    with pytest.raises(ValueError, match="different source commit"):
        verify_precommitted_extraction_source_archive_provenance_for_run(
            trust_policy=policy,
            trust_root=trust_root,
            signed_provenance=signed,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha="b" * 40,
        )


def test_source_archive_signed_subject_must_match_exact_source_tree() -> None:
    policy, trust_root, execution_plan, signed = _source_archive_fixture()
    tampered = replace(
        signed,
        statement=replace(signed.statement, source_tree_sha256="9" * 64),
    )

    with pytest.raises(ValueError, match="subject or builder identity"):
        verify_precommitted_extraction_source_archive_provenance_for_run(
            trust_policy=policy,
            trust_root=trust_root,
            signed_provenance=tampered,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha=_COMMIT_SHA,
        )


def test_source_archive_signature_cannot_be_replayed_for_different_build_run() -> None:
    policy, trust_root, execution_plan, signed = _source_archive_fixture()
    tampered = replace(signed, statement=replace(signed.statement, run_id="other-run"))

    with pytest.raises(ValueError, match="run_id differs"):
        verify_precommitted_extraction_source_archive_provenance_for_run(
            trust_policy=policy,
            trust_root=trust_root,
            signed_provenance=tampered,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha=_COMMIT_SHA,
        )


def test_source_archive_wrong_signing_key_fails_closed() -> None:
    policy, trust_root, execution_plan, signed = _source_archive_fixture()
    _, other_public_key_hex = _keypair()
    wrong_root = replace(trust_root, public_key_hex=other_public_key_hex)
    rebound_policy = replace(policy, trust_root_sha256=wrong_root.sha256())
    rebound_statement = replace(signed.statement, trust_root_sha256=wrong_root.sha256())
    rebound_signed = replace(signed, statement=rebound_statement)

    with pytest.raises(ValueError, match="signature is invalid"):
        verify_precommitted_extraction_source_archive_provenance_for_run(
            trust_policy=rebound_policy,
            trust_root=wrong_root,
            signed_provenance=rebound_signed,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha=_COMMIT_SHA,
        )


def test_source_archive_policy_and_receipt_remain_nonproduction() -> None:
    policy, trust_root, execution_plan, signed = _source_archive_fixture()
    with pytest.raises(ValueError, match="non-production"):
        replace(policy, production_authorized=True)

    receipt = verify_precommitted_extraction_source_archive_provenance_for_run(
        trust_policy=policy,
        trust_root=trust_root,
        signed_provenance=signed,
        execution_plan=execution_plan,
        expected_run_id=signed.statement.run_id,
        expected_run_attempt=signed.statement.run_attempt,
        expected_commit_sha=_COMMIT_SHA,
    )
    with pytest.raises(ValueError, match="non-production"):
        replace(receipt, production_authorized=True)
