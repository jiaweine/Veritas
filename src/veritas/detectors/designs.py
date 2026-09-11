from __future__ import annotations

from uuid import uuid4

from ..models import CheckResult, DIDDesign, Finding, IVDesign
from ..types import CheckStatus, EvidenceFamily, EvidenceGrade
from .base import Detector

_TWFE_NAMES = {"twfe", "two_way_fixed_effects", "two-way fixed effects", "event_study_twfe"}
_WEAK_ROBUST_METHODS = {"anderson-rubin", "anderson_rubin", "ar", "tf", "tF"}


class DIDDesignDetector(Detector):
    detector_id = "did_design_frontier"
    version = "0.1.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, DIDDesign)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, DIDDesign)
        estimator = (obj.estimator or "").strip().lower()

        if obj.periods == 2 and obj.staggered_adoption is False and obj.treatment_type == "binary":
            return [self._pass(obj, "Canonical two-group/two-period structure does not trigger modern staggered-DiD linting.")]

        if obj.treatment_type == "continuous" and estimator in _TWFE_NAMES:
            return [
                self._review(
                    obj,
                    "continuous_twfe",
                    "Continuous-treatment DiD with a vanilla TWFE summary requires careful estimand interpretation; "
                    "modern results show that popular TWFE estimands can have multiple limited interpretations.",
                    {
                        "method_anchor": "Callaway, Goodman-Bacon & Sant'Anna, AER forthcoming (2026 listing)",
                        "estimator": obj.estimator,
                    },
                )
            ]

        if obj.staggered_adoption is None:
            return [self._unverifiable(obj, "Treatment timing could not be resolved from available material.")]

        if obj.staggered_adoption and estimator in _TWFE_NAMES:
            if obj.heterogeneity_robust_estimator_reported is True:
                return [
                    self._pass(
                        obj,
                        "Staggered adoption is present, but the paper also reports a heterogeneity-robust estimator for comparison.",
                    )
                ]
            if obj.event_study is True or obj.heterogeneity_robust_estimator_reported is False:
                return [
                    self._review(
                        obj,
                        "staggered_twfe",
                        "Staggered-adoption DiD is summarized with TWFE without a reported heterogeneity-robust comparison. "
                        "This is a design-risk flag, not a claim that TWFE is automatically invalid.",
                        {
                            "method_anchor": "Baker et al., Journal of Economic Literature 2026; Borusyak, Jaravel & Spiess, ReStud 2024",
                            "event_study": obj.event_study,
                            "comparison_group": obj.comparison_group,
                        },
                    )
                ]
        return [self._pass(obj, "No currently encoded high-priority DiD design incompatibility was detected.")]

    def _pass(self, obj: DIDDesign, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "design_compatibility",
            obj.object_id,
            CheckStatus.PASS,
            EvidenceFamily.DESIGN_VALIDITY,
            message=message,
        )

    def _unverifiable(self, obj: DIDDesign, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "design_compatibility",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.DESIGN_VALIDITY,
            message=message,
        )

    def _review(self, obj: DIDDesign, check_id: str, explanation: str, evidence: dict[str, object]) -> CheckResult:
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.METHODOLOGICAL_RISK,
            materiality=obj.materiality,
            family=EvidenceFamily.DESIGN_VALIDITY,
            title="Difference-in-differences design risk",
            explanation=explanation,
            evidence=evidence,
            detector_precision=0.7,
            source=obj.source,
        )
        return CheckResult(
            self.detector_id,
            check_id,
            obj.object_id,
            CheckStatus.REVIEW,
            EvidenceFamily.DESIGN_VALIDITY,
            message=explanation,
            finding=finding,
        )


class WeakIVDesignDetector(Detector):
    detector_id = "weak_iv_frontier"
    version = "0.1.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, IVDesign)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, IVDesign)
        normalized = {method.strip().lower() for method in obj.weak_robust_methods}
        has_robust = bool(normalized & {method.lower() for method in _WEAK_ROBUST_METHODS})

        if has_robust:
            return [self._pass(obj, "Weak-instrument-robust inference is reported (e.g., Anderson-Rubin or tF).")]

        if obj.uses_f_gt_10_rule_as_validity_claim:
            return [
                self._review(
                    obj,
                    "f_gt_10_rule",
                    "The paper treats F > 10 as a validity rule for a single-IV design. Current guidance explicitly warns that this popular threshold has no general theoretical justification in this setting; weak-IV-robust inference should be examined instead.",
                    {
                        "reported_first_stage_f": obj.first_stage_f.value if obj.first_stage_f else None,
                        "method_anchor": "Lee & Porter, Journal of Economic Perspectives 2026",
                    },
                )
            ]

        if obj.single_instrument is True and obj.single_endogenous_regressor is True:
            if obj.first_stage_f is None:
                return [self._unverifiable(obj, "First-stage strength and weak-IV-robust inference are not sufficiently reported.")]
            return [
                self._review(
                    obj,
                    "robust_inference_missing",
                    "A just-identified single-IV result is reported without an encoded weak-IV-robust inference method. Veritas does not use a hard F-statistic cutoff; it requests Anderson-Rubin/tF-style robustness instead.",
                    {
                        "reported_first_stage_f": obj.first_stage_f.value,
                        "no_hard_f_threshold_used": True,
                        "method_anchor": "Lee & Porter, Journal of Economic Perspectives 2026",
                    },
                )
            ]
        return [self._unverifiable(obj, "Current weak-IV detector is scoped to the single-instrument/single-endogenous-regressor case.")]

    def _pass(self, obj: IVDesign, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "weak_iv_inference",
            obj.object_id,
            CheckStatus.PASS,
            EvidenceFamily.DESIGN_VALIDITY,
            message=message,
        )

    def _unverifiable(self, obj: IVDesign, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "weak_iv_inference",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.DESIGN_VALIDITY,
            message=message,
        )

    def _review(self, obj: IVDesign, check_id: str, explanation: str, evidence: dict[str, object]) -> CheckResult:
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.METHODOLOGICAL_RISK,
            materiality=obj.materiality,
            family=EvidenceFamily.DESIGN_VALIDITY,
            title="Weak-instrument inference risk",
            explanation=explanation,
            evidence=evidence,
            detector_precision=0.7,
            source=obj.source,
        )
        return CheckResult(
            self.detector_id,
            check_id,
            obj.object_id,
            CheckStatus.REVIEW,
            EvidenceFamily.DESIGN_VALIDITY,
            message=explanation,
            finding=finding,
        )
