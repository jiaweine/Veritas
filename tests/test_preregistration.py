from __future__ import annotations

import pytest

from veritas.models import SourceLocation
from veritas.preregistration import (
    ObservedAnalysisItem,
    PlanComparisonStatus,
    PlanItemKind,
    RegisteredPlanItem,
    RegistrationKind,
    RegistrationPlan,
    compare_registration_plan,
)


def _plan(*, verified: bool = True) -> RegistrationPlan:
    return RegistrationPlan(
        "osf-plan",
        RegistrationKind.PREREGISTRATION,
        "a" * 64,
        (
            RegisteredPlanItem(
                "model-main",
                PlanItemKind.MODEL,
                "OLS with treatment and baseline controls",
                SourceLocation(artifact_id="registration", section="Analysis"),
            ),
            RegisteredPlanItem(
                "exclude-missing",
                PlanItemKind.EXCLUSION,
                "Exclude records missing the primary outcome",
                SourceLocation(artifact_id="registration", section="Sample"),
            ),
        ),
        SourceLocation(artifact_id="registration"),
        verified,
    )


def test_registration_plan_reports_match_deviation_and_undeclared_separately() -> None:
    observed = (
        ObservedAnalysisItem(
            "observed-model",
            PlanItemKind.MODEL,
            "  ols WITH treatment and baseline controls ",
            SourceLocation(artifact_id="code", section="model"),
            "model-main",
        ),
        ObservedAnalysisItem(
            "observed-exclusion",
            PlanItemKind.EXCLUSION,
            "Exclude records missing any covariate",
            SourceLocation(artifact_id="code", section="filter"),
            "exclude-missing",
        ),
        ObservedAnalysisItem(
            "observed-transform",
            PlanItemKind.TRANSFORMATION,
            "Winsorize outcome at 1% and 99%",
            SourceLocation(artifact_id="code", section="transform"),
        ),
    )

    report = compare_registration_plan(_plan(), observed)

    assert [item.status for item in report.comparisons] == [
        PlanComparisonStatus.MATCH,
        PlanComparisonStatus.DEVIATION,
        PlanComparisonStatus.UNDECLARED,
    ]
    assert len(report.deviations) == 2
    assert report.fully_verifiable is True


def test_unverified_registration_identity_fails_closed() -> None:
    observed = (
        ObservedAnalysisItem(
            "observed-model",
            PlanItemKind.MODEL,
            "OLS with treatment and baseline controls",
            SourceLocation(artifact_id="code"),
            "model-main",
        ),
    )

    report = compare_registration_plan(_plan(verified=False), observed)

    assert report.comparisons[0].status is PlanComparisonStatus.UNVERIFIABLE
    assert report.fully_verifiable is False


def test_low_confidence_observed_analysis_fails_closed() -> None:
    observed = (
        ObservedAnalysisItem(
            "observed-model",
            PlanItemKind.MODEL,
            "OLS with treatment and baseline controls",
            SourceLocation(artifact_id="code"),
            "model-main",
            extraction_confidence=0.40,
        ),
    )

    report = compare_registration_plan(_plan(), observed)

    assert report.comparisons[0].status is PlanComparisonStatus.UNVERIFIABLE


def test_multiple_observations_cannot_claim_same_registered_item() -> None:
    observed = (
        ObservedAnalysisItem(
            "one",
            PlanItemKind.MODEL,
            "OLS with treatment and baseline controls",
            SourceLocation(artifact_id="code"),
            "model-main",
        ),
        ObservedAnalysisItem(
            "two",
            PlanItemKind.MODEL,
            "OLS with treatment and baseline controls",
            SourceLocation(artifact_id="code"),
            "model-main",
        ),
    )

    with pytest.raises(ValueError, match="multiple observations"):
        compare_registration_plan(_plan(), observed)
