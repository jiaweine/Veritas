from __future__ import annotations

from dataclasses import asdict

from .models import CheckResult, Finding, SourceLocation
from .reproduction import (
    ReproductionDecision,
    ReproductionReport,
)
from .types import CheckStatus, EvidenceFamily, EvidenceGrade, Materiality


def build_reproduction_e4_check(
    report: ReproductionReport,
    *,
    object_id: str,
    source: SourceLocation,
    finding_id: str = "reproduction:e4",
) -> CheckResult:
    """Convert only immutable, fully attested reproduction evidence into an E4 audit check."""

    if report.evidence_binding is None:
        raise ValueError("E4 audit path requires immutable reproduction evidence binding")
    if not (
        report.method_fidelity_verified
        and report.artifact_identity_verified
        and report.execution_attested
    ):
        raise ValueError("E4 audit path requires the complete verified reproduction chain")

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
        raise ValueError("mismatch report lacks E4 reproduction-contradiction authority")

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
