from __future__ import annotations

from dataclasses import asdict

from .models import CheckResult, Finding, SourceLocation
from .reproduction import (
    CodeAgentProposal,
    CodeAgentTask,
    ExecutionAttestation,
    MethodFidelityAttestation,
    ReproductionAuthority,
    ReproductionDecision,
    ReproductionReport,
    ReproductionRootCause,
    ReproductionTarget,
    SandboxPolicy,
)
from .reproduction_attestation import (
    ArtifactIdentityAttestation,
    build_attested_reproduction_report,
)
from .types import CheckStatus, EvidenceFamily, EvidenceGrade, Materiality


def build_attested_reproduction_e4_check(
    comparisons,
    *,
    task: CodeAgentTask,
    targets: tuple[ReproductionTarget, ...],
    proposal: CodeAgentProposal,
    sandbox_policy: SandboxPolicy,
    execution: ExecutionAttestation,
    method_fidelity: MethodFidelityAttestation,
    artifact_identity: ArtifactIdentityAttestation,
    authority: ReproductionAuthority,
    object_id: str,
    source: SourceLocation,
    root_cause: ReproductionRootCause = ReproductionRootCause.UNKNOWN,
    finding_id: str = "reproduction:e4",
) -> CheckResult:
    """Canonical E4 audit path; callers cannot inject a hand-built ReproductionReport."""

    report = build_attested_reproduction_report(
        comparisons,
        task=task,
        targets=targets,
        proposal=proposal,
        sandbox_policy=sandbox_policy,
        execution=execution,
        method_fidelity=method_fidelity,
        artifact_identity=artifact_identity,
        authority=authority,
        root_cause=root_cause,
    )
    return _check_from_attested_report(
        report,
        object_id=object_id,
        source=source,
        finding_id=finding_id,
    )


def _check_from_attested_report(
    report: ReproductionReport,
    *,
    object_id: str,
    source: SourceLocation,
    finding_id: str,
) -> CheckResult:
    if report.evidence_binding is None:
        raise RuntimeError("canonical attested report unexpectedly lacks evidence binding")

    if report.decision is ReproductionDecision.MATCH:
        return CheckResult(
            detector_id="reproduction_attested_v1",
            check_id="attested_reproduction_match",
            object_id=object_id,
            status=CheckStatus.PASS,
            family=EvidenceFamily.REPRODUCTION,
            message="fully attested reproduction matched the sealed target set",
        )
    if report.decision is ReproductionDecision.PARTIAL:
        return CheckResult(
            detector_id="reproduction_attested_v1",
            check_id="attested_reproduction_partial",
            object_id=object_id,
            status=CheckStatus.REVIEW,
            family=EvidenceFamily.REPRODUCTION,
            message="fully attested reproduction is incomplete; missing targets prevent a hard conclusion",
        )
    if report.decision is ReproductionDecision.UNVERIFIABLE:
        return CheckResult(
            detector_id="reproduction_attested_v1",
            check_id="attested_reproduction_unverifiable",
            object_id=object_id,
            status=CheckStatus.UNVERIFIABLE,
            family=EvidenceFamily.REPRODUCTION,
            message="fully attested reproduction contains no comparable result",
        )

    if report.max_evidence_grade is not EvidenceGrade.REPRODUCTION_CONTRADICTION:
        raise RuntimeError("canonical mismatch report unexpectedly lacks E4 authority")

    materiality = report.agreement.max_mismatch_materiality or Materiality.SECONDARY_RESULT
    evidence = {
        "authority": report.authority.value,
        "root_cause": report.root_cause.value,
        "mismatch_target_ids": [
            comparison.target_id
            for comparison in report.comparisons
            if comparison.status.value == "mismatch"
        ],
        "comparison_statuses": {
            comparison.target_id: comparison.status.value
            for comparison in report.comparisons
        },
        "agreement": {
            "total_targets": report.agreement.total_targets,
            "matched_targets": report.agreement.matched_targets,
            "mismatched_targets": report.agreement.mismatched_targets,
            "missing_targets": report.agreement.missing_targets,
            "material_mismatch_target_ids": list(
                report.agreement.material_mismatch_target_ids
            ),
        },
        "evidence_binding": asdict(report.evidence_binding),
        "numeric_values_persisted_in_finding": False,
    }
    finding = Finding(
        finding_id=finding_id,
        detector_id="reproduction_attested_v1",
        object_id=object_id,
        grade=EvidenceGrade.REPRODUCTION_CONTRADICTION,
        materiality=materiality,
        family=EvidenceFamily.REPRODUCTION,
        title="Fully attested reproduction contradicts the reported result",
        explanation=(
            "A frozen, independently attested reproduction run produced one or more values that "
            "fall outside the sealed reported-value compatibility interval. Numeric answers are "
            "not copied into this finding; immutable task, environment, input, code, and output "
            "hashes bind the evidence."
        ),
        evidence=evidence,
        source=source,
    )
    return CheckResult(
        detector_id="reproduction_attested_v1",
        check_id="attested_reproduction_mismatch",
        object_id=object_id,
        status=CheckStatus.FAIL,
        family=EvidenceFamily.REPRODUCTION,
        message="fully attested reproduction mismatch",
        finding=finding,
    )
