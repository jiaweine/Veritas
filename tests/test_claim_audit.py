from __future__ import annotations

import pytest

from veritas.claim_audit import bind_cross_location_claim_findings
from veritas.claim_identity import (
    build_claim_estimate_alignment,
    normalize_estimand_identity,
)
from veritas.claims import (
    ArtifactRef,
    ClaimNode,
    ClaimRole,
    ExtractedField,
    StatisticalClaimGraph,
    StatisticalObjectNode,
)
from veritas.models import AuditSummary, CheckResult, Finding, SourceLocation
from veritas.types import CheckStatus, EvidenceFamily, EvidenceGrade, Materiality


def _alignment(*, transformation: str = "level", estimate_transformation: str = "level"):
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf"))
    graph.add_claim(
        ClaimNode(
            "claim",
            "The program increased employment.",
            ClaimRole.PRIMARY,
            SourceLocation(artifact_id="paper", page=2, section="Abstract"),
            extraction_confidence=0.98,
        )
    )
    graph.add_object(
        StatisticalObjectNode(
            "estimate",
            "RegressionResult",
            {
                "beta": ExtractedField(
                    "0.10",
                    0.10,
                    SourceLocation(artifact_id="paper", page=8, table="Table 3"),
                    0.98,
                )
            },
            SourceLocation(artifact_id="paper", page=8, table="Table 3"),
        )
    )
    return build_claim_estimate_alignment(
        graph,
        claim_id="claim",
        estimate_object_id="estimate",
        claim_identity=normalize_estimand_identity(
            outcome="employment",
            treatment="program",
            transformation=transformation,
        ),
        estimate_identity=normalize_estimand_identity(
            outcome="employment",
            treatment="program",
            transformation=estimate_transformation,
        ),
    )


def _summary(*, grade: EvidenceGrade = EvidenceGrade.INTERNAL_CONTRADICTION, object_id: str = "estimate"):
    finding = Finding(
        finding_id="finding-1",
        detector_id="detector",
        object_id=object_id,
        grade=grade,
        materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        family=EvidenceFamily.NUMERICAL_CONSISTENCY,
        title="contradiction",
        explanation="reported values cannot all be true",
        source=SourceLocation(artifact_id="paper", page=8, table="Table 3"),
    )
    check = CheckResult(
        detector_id="detector",
        check_id="check",
        object_id=object_id,
        status=CheckStatus.FAIL,
        family=EvidenceFamily.NUMERICAL_CONSISTENCY,
        finding=finding,
    )
    return AuditSummary(1.0, 1.0, (finding,), (check,))


def test_cross_location_e3_binding_records_both_sources_and_identity() -> None:
    rebound = bind_cross_location_claim_findings(_summary(), _alignment())

    binding = rebound.findings[0].evidence["claim_identity_binding"]
    assert binding["claim_id"] == "claim"
    assert binding["identity_confidence"] == 0.90
    assert binding["claim_source"]["page"] == 2
    assert binding["estimate_source"]["page"] == 8
    assert rebound.checks[0].finding is rebound.findings[0]


def test_cross_location_e3_binding_rejects_scale_mismatch() -> None:
    with pytest.raises(ValueError, match="high-confidence claim/estimand identity"):
        bind_cross_location_claim_findings(
            _summary(),
            _alignment(transformation="percentage points", estimate_transformation="percent"),
        )


def test_cross_location_e3_binding_rejects_wrong_object_identity() -> None:
    with pytest.raises(ValueError, match="does not match hard finding"):
        bind_cross_location_claim_findings(_summary(object_id="different"), _alignment())


def test_lower_grade_object_signal_does_not_require_cross_location_identity() -> None:
    rebound = bind_cross_location_claim_findings(
        _summary(grade=EvidenceGrade.METHODOLOGICAL_RISK),
        _alignment(transformation="percentage points", estimate_transformation="percent"),
    )

    assert "claim_identity_binding" not in rebound.findings[0].evidence
