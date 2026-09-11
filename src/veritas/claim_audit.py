from __future__ import annotations

from dataclasses import asdict, replace

from .claim_identity import ClaimEstimateAlignment, require_cross_location_e3_identity
from .models import AuditSummary, CheckResult, Finding
from .types import EvidenceGrade


def bind_cross_location_claim_findings(
    summary: AuditSummary,
    alignment: ClaimEstimateAlignment,
    *,
    minimum_identity_confidence: float = 0.90,
    minimum_effective_confidence: float = 0.90,
) -> AuditSummary:
    """Bind E3+ object findings to a publication claim only after identity is verified.

    Object-level detector results remain valid without this function. This constructor is the
    fail-closed boundary for claiming that a finding at one source location contradicts or bears on
    a claim at another source location.
    """

    hard_findings = tuple(
        finding for finding in summary.findings if finding.grade >= EvidenceGrade.INTERNAL_CONTRADICTION
    )
    if hard_findings:
        require_cross_location_e3_identity(
            alignment,
            minimum_identity_confidence=minimum_identity_confidence,
            minimum_effective_confidence=minimum_effective_confidence,
        )
    mismatched = tuple(
        finding.object_id
        for finding in hard_findings
        if finding.object_id != alignment.estimate_object_id
    )
    if mismatched:
        raise ValueError(
            "claim alignment estimate_object_id does not match hard finding object ids: "
            f"{mismatched!r}"
        )

    binding = {
        "claim_id": alignment.claim_id,
        "estimate_object_id": alignment.estimate_object_id,
        "identity_confidence": alignment.identity_match.confidence,
        "identity_matched_dimensions": list(alignment.identity_match.matched_dimensions),
        "identity_conflicting_dimensions": list(alignment.identity_match.conflicting_dimensions),
        "identity_unresolved_dimensions": list(alignment.identity_match.unresolved_dimensions),
        "extraction_confidence": alignment.extraction_confidence,
        "matcher_confidence": alignment.matcher_confidence,
        "effective_confidence": alignment.effective_confidence,
        "claim_source": asdict(alignment.claim_source),
        "estimate_source": asdict(alignment.estimate_source),
    }

    findings_by_id: dict[str, Finding] = {}
    rebound_findings: list[Finding] = []
    for finding in summary.findings:
        rebound = finding
        if finding.grade >= EvidenceGrade.INTERNAL_CONTRADICTION:
            rebound = replace(
                finding,
                evidence={**finding.evidence, "claim_identity_binding": binding},
            )
        findings_by_id[finding.finding_id] = rebound
        rebound_findings.append(rebound)

    rebound_checks: list[CheckResult] = []
    for check in summary.checks:
        if check.finding is None:
            rebound_checks.append(check)
            continue
        rebound_checks.append(
            replace(check, finding=findings_by_id[check.finding.finding_id])
        )

    return replace(
        summary,
        findings=tuple(rebound_findings),
        checks=tuple(rebound_checks),
    )
