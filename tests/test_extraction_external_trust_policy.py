from __future__ import annotations

from dataclasses import replace

import pytest
from test_extraction_external_provenance import _signed_fixture

from veritas.extraction_external_trust_policy import (
    build_extraction_external_trust_policy,
    verify_precommitted_external_extraction_provenance_for_run,
)


def _policy_fixture():
    trust_root, execution_plan, attested_release, signed = _signed_fixture()
    evidence_plan_sha256 = attested_release.evidence_plan_sha256
    policy = build_extraction_external_trust_policy(
        policy_id="real-extraction-run-v1",
        evidence_plan_sha256=evidence_plan_sha256,
        trust_root=trust_root,
    )
    return (
        policy,
        evidence_plan_sha256,
        trust_root,
        execution_plan,
        attested_release,
        signed,
    )


def test_precommitted_policy_binds_plan_root_and_verified_run() -> None:
    policy, evidence_plan_sha256, trust_root, execution_plan, attested_release, signed = (
        _policy_fixture()
    )
    receipt = verify_precommitted_external_extraction_provenance_for_run(
        trust_policy=policy,
        evidence_plan_sha256=evidence_plan_sha256,
        trust_root=trust_root,
        signed_provenance=signed,
        attested_release_receipt=attested_release,
        execution_plan=execution_plan,
        expected_run_id=signed.statement.run_id,
        expected_run_attempt=signed.statement.run_attempt,
        expected_commit_sha=signed.statement.commit_sha,
    )

    assert receipt.production_authorized is False
    assert receipt.trust_policy_sha256 == policy.sha256()
    assert receipt.evidence_plan_sha256 == evidence_plan_sha256
    assert receipt.trust_root_sha256 == trust_root.sha256()
    assert len(receipt.verified_run_receipt_sha256) == 64
    assert len(receipt.sha256()) == 64


def test_posthoc_different_trust_root_cannot_satisfy_precommitted_policy() -> None:
    policy, evidence_plan_sha256, trust_root, execution_plan, attested_release, signed = (
        _policy_fixture()
    )
    changed_root = replace(trust_root, public_key_hex="9" * 64)

    with pytest.raises(ValueError, match="different trust root"):
        verify_precommitted_external_extraction_provenance_for_run(
            trust_policy=policy,
            evidence_plan_sha256=evidence_plan_sha256,
            trust_root=changed_root,
            signed_provenance=signed,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha=signed.statement.commit_sha,
        )


def test_policy_cannot_be_reused_for_different_evidence_plan() -> None:
    policy, _, trust_root, execution_plan, attested_release, signed = _policy_fixture()
    with pytest.raises(ValueError, match="different evidence plan"):
        verify_precommitted_external_extraction_provenance_for_run(
            trust_policy=policy,
            evidence_plan_sha256="f" * 64,
            trust_root=trust_root,
            signed_provenance=signed,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha=signed.statement.commit_sha,
        )


def test_policy_rejects_signed_release_bound_to_different_evidence_plan() -> None:
    policy, evidence_plan_sha256, trust_root, execution_plan, attested_release, signed = (
        _policy_fixture()
    )
    drifted_release = replace(attested_release, evidence_plan_sha256="f" * 64)

    with pytest.raises(ValueError, match="signed attested release"):
        verify_precommitted_external_extraction_provenance_for_run(
            trust_policy=policy,
            evidence_plan_sha256=evidence_plan_sha256,
            trust_root=trust_root,
            signed_provenance=signed,
            attested_release_receipt=drifted_release,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha=signed.statement.commit_sha,
        )


def test_policy_identity_drift_fails_closed_even_with_same_hash_fields() -> None:
    policy, evidence_plan_sha256, trust_root, execution_plan, attested_release, signed = (
        _policy_fixture()
    )
    drifted = replace(policy, workflow_identity="different-workflow")
    with pytest.raises(ValueError, match="runner identity differs"):
        verify_precommitted_external_extraction_provenance_for_run(
            trust_policy=drifted,
            evidence_plan_sha256=evidence_plan_sha256,
            trust_root=trust_root,
            signed_provenance=signed,
            attested_release_receipt=attested_release,
            execution_plan=execution_plan,
            expected_run_id=signed.statement.run_id,
            expected_run_attempt=signed.statement.run_attempt,
            expected_commit_sha=signed.statement.commit_sha,
        )


def test_policy_and_receipt_authority_remain_nonproduction() -> None:
    policy, evidence_plan_sha256, trust_root, execution_plan, attested_release, signed = (
        _policy_fixture()
    )
    with pytest.raises(ValueError, match="non-production"):
        replace(policy, production_authorized=True)

    receipt = verify_precommitted_external_extraction_provenance_for_run(
        trust_policy=policy,
        evidence_plan_sha256=evidence_plan_sha256,
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
