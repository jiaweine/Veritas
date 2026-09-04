from __future__ import annotations

from dataclasses import replace

import pytest
from test_extraction_evidence_workflow import _workflow_fixture

from veritas.benchmark import BenchmarkSplit
from veritas.extraction_execution_evidence import (
    ExtractionExecutionEvidence,
    ExtractionExecutionPlan,
    build_attested_extraction_evidence_release_receipt,
    build_extraction_execution_evidence,
    extraction_prediction_artifact_bytes,
)


def _execution_plan() -> ExtractionExecutionPlan:
    return ExtractionExecutionPlan(
        input_artifact_manifest_sha256="1" * 64,
        source_tree_sha256="2" * 64,
        parser_registry_sha256="3" * 64,
        numerical_runtime_sha256="4" * 64,
        execution_command_sha256="5" * 64,
    )


def _evidence_set(fixture, *, split: BenchmarkSplit, plan: ExtractionExecutionPlan):
    if split is BenchmarkSplit.DEVELOPMENT:
        observations = fixture["observations"]
        target_manifest_sha256 = fixture["development_manifest"].sha256()
    else:
        observations = fixture["test_observations"]
        target_manifest_sha256 = fixture["test_manifest"].sha256()

    return tuple(
        build_extraction_execution_evidence(
            plan=plan,
            execution_id=f"{split.value}-{observation.threshold_id}",
            split=split,
            threshold_id=observation.threshold_id,
            threshold=observation.threshold,
            target_manifest_sha256=target_manifest_sha256,
            predictions=observation.predictions or (),
            prediction_artifact=extraction_prediction_artifact_bytes(
                observation.predictions or ()
            ),
        )
        for observation in observations
    )


def _attested_release(**overrides):
    fixture = _workflow_fixture()
    execution_plan = overrides.pop("execution_plan", _execution_plan())
    development_execution_evidence = overrides.pop(
        "development_execution_evidence",
        _evidence_set(fixture, split=BenchmarkSplit.DEVELOPMENT, plan=execution_plan),
    )
    test_execution_evidence = overrides.pop(
        "test_execution_evidence",
        _evidence_set(fixture, split=BenchmarkSplit.TEST, plan=execution_plan),
    )
    fixture.update(overrides)
    return build_attested_extraction_evidence_release_receipt(
        execution_plan=execution_plan,
        development_execution_evidence=development_execution_evidence,
        test_execution_evidence=test_execution_evidence,
        plan=fixture["plan"],
        sampling_frame=fixture["frame"],
        seed_manifest=fixture["seed"],
        threshold_grid=fixture["grid"],
        gold_manifest=fixture["gold"],
        review_records=fixture["review_records"],
        split_lock=fixture["split_lock"],
        threshold_policy=fixture["policy"],
        development_observations=fixture["observations"],
        test_observations=fixture["test_observations"],
        frozen_threshold=fixture["frozen"],
        test_seal=fixture["test_seal"],
        test_evaluation_lock=fixture["test_lock"],
        development_curve=fixture["development_curve"],
        test_curve=fixture["test_curve"],
    )


def test_attested_release_binds_base_release_and_execution_sets() -> None:
    first = _attested_release()
    second = _attested_release()

    assert first.production_authorized is False
    assert len(first.base_release_receipt_sha256) == 64
    assert len(first.execution_plan_sha256) == 64
    assert len(first.development_execution_set_sha256) == 64
    assert len(first.test_execution_set_sha256) == 64
    assert first.development_execution_set_sha256 != first.test_execution_set_sha256
    assert first.sha256() == second.sha256()


def test_attested_release_requires_execution_evidence_for_every_threshold() -> None:
    fixture = _workflow_fixture()
    plan = _execution_plan()
    development = _evidence_set(
        fixture,
        split=BenchmarkSplit.DEVELOPMENT,
        plan=plan,
    )

    with pytest.raises(ValueError, match="threshold observation membership"):
        _attested_release(
            execution_plan=plan,
            development_execution_evidence=development[:-1],
        )


def test_attested_release_rejects_execution_plan_drift() -> None:
    fixture = _workflow_fixture()
    original_plan = _execution_plan()
    changed_plan = replace(original_plan, source_tree_sha256="9" * 64)
    development = _evidence_set(
        fixture,
        split=BenchmarkSplit.DEVELOPMENT,
        plan=original_plan,
    )
    test = _evidence_set(
        fixture,
        split=BenchmarkSplit.TEST,
        plan=original_plan,
    )

    with pytest.raises(ValueError, match="different execution plan"):
        _attested_release(
            execution_plan=changed_plan,
            development_execution_evidence=development,
            test_execution_evidence=test,
        )


def test_attested_release_rejects_target_manifest_drift() -> None:
    fixture = _workflow_fixture()
    plan = _execution_plan()
    development = list(
        _evidence_set(fixture, split=BenchmarkSplit.DEVELOPMENT, plan=plan)
    )
    first = development[0]
    development[0] = ExtractionExecutionEvidence(
        attestation=replace(first.attestation, target_manifest_sha256="a" * 64),
        prediction_artifact=first.prediction_artifact,
    )

    with pytest.raises(ValueError, match="different target manifest"):
        _attested_release(
            execution_plan=plan,
            development_execution_evidence=tuple(development),
        )


def test_execution_evidence_rejects_changed_prediction_artifact_bytes() -> None:
    fixture = _workflow_fixture()
    plan = _execution_plan()
    observation = fixture["observations"][0]
    artifact = extraction_prediction_artifact_bytes(observation.predictions or ())

    with pytest.raises(ValueError, match="canonical extraction prediction JSON"):
        build_extraction_execution_evidence(
            plan=plan,
            execution_id="dev-tampered",
            split=BenchmarkSplit.DEVELOPMENT,
            threshold_id=observation.threshold_id,
            threshold=observation.threshold,
            target_manifest_sha256=fixture["development_manifest"].sha256(),
            predictions=observation.predictions or (),
            prediction_artifact=artifact + b"\n",
        )


def test_attested_release_rejects_forged_prediction_semantics_digest() -> None:
    fixture = _workflow_fixture()
    plan = _execution_plan()
    development = list(
        _evidence_set(fixture, split=BenchmarkSplit.DEVELOPMENT, plan=plan)
    )
    first = development[0]
    development[0] = ExtractionExecutionEvidence(
        attestation=replace(first.attestation, prediction_semantics_sha256="f" * 64),
        prediction_artifact=first.prediction_artifact,
    )

    with pytest.raises(ValueError, match="prediction semantics differ"):
        _attested_release(
            execution_plan=plan,
            development_execution_evidence=tuple(development),
        )


def test_execution_plan_and_attestation_security_controls_fail_closed() -> None:
    with pytest.raises(ValueError, match="disable network"):
        replace(_execution_plan(), network_disabled=False)
    with pytest.raises(ValueError, match="read-only"):
        replace(_execution_plan(), source_mount_read_only=False)
    with pytest.raises(ValueError, match="must not mount credentials"):
        replace(_execution_plan(), credentials_mounted=True)

    fixture = _workflow_fixture()
    plan = _execution_plan()
    evidence = _evidence_set(
        fixture,
        split=BenchmarkSplit.DEVELOPMENT,
        plan=plan,
    )[0]
    with pytest.raises(ValueError, match="exit successfully"):
        replace(evidence.attestation, exit_code=1)
    with pytest.raises(ValueError, match="disabled network"):
        replace(evidence.attestation, network_disabled=False)
    with pytest.raises(ValueError, match="no mounted credentials"):
        replace(evidence.attestation, credentials_mounted=True)
