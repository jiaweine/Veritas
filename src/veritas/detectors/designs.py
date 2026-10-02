from __future__ import annotations

from uuid import uuid4

from ..methodology import get_method_anchor
from ..models import CheckResult, DIDDesign, Finding, IVDesign
from ..types import CheckStatus, EvidenceFamily, EvidenceGrade
from .base import Detector

_TWFE_NAMES = {"twfe", "two_way_fixed_effects", "two-way fixed effects", "event_study_twfe"}
_WEAK_ROBUST_METHODS = {"anderson-rubin", "anderson_rubin", "ar", "tf", "t-f", "t_f"}
_POINTWISE_PRETREND_NAMES = {"pointwise", "individual", "lead-by-lead", "lead_by_lead"}


class DIDDesignDetector(Detector):
    """Paper-only DiD design linting.

    The detector intentionally emits methodological-risk review findings only. It
    does not turn a method name, a failed pre-trend test, or a TWFE specification
    into evidence of an internal contradiction or author intent.
    """

    detector_id = "did_design_frontier"
    version = "0.2.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, DIDDesign)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, DIDDesign)
        estimator = _normalized(obj.estimator)
        pretrend = _normalized(obj.pretrend_test)

        if obj.periods == 2 and obj.staggered_adoption is False and obj.treatment_type == "binary":
            return [
                self._pass(
                    obj,
                    "Canonical two-group/two-period structure does not trigger modern staggered-DiD linting.",
                )
            ]

        if obj.parallel_trends_claimed is True and pretrend in _POINTWISE_PRETREND_NAMES:
            return [
                self._review(
                    obj,
                    "pointwise_pretrend_overclaim",
                    "Pointwise pre-treatment significance checks are reported as support for a stronger parallel-trends claim. "
                    "Such checks can be informative diagnostics, but they do not by themselves establish the identifying assumption.",
                    {
                        "pretrend_test": obj.pretrend_test,
                        "parallel_trends_claimed": True,
                        "event_time_window": obj.event_time_window,
                        "method_anchor": get_method_anchor("did_jel_2026").key,
                    },
                )
            ]

        if obj.treatment_type == "continuous" and estimator in _TWFE_NAMES:
            return [
                self._review(
                    obj,
                    "continuous_twfe",
                    "Continuous-treatment DiD with a vanilla TWFE summary requires careful estimand interpretation; "
                    "the encoded paper-only evidence is insufficient to treat the TWFE coefficient as a generic treatment effect.",
                    {
                        "estimator": obj.estimator,
                        "treatment_timing": obj.treatment_timing,
                        "comparison_group": obj.comparison_group,
                        "method_anchor": get_method_anchor("did_continuous_2026").key,
                    },
                )
            ]

        if obj.staggered_adoption is None:
            return [
                self._unverifiable(
                    obj,
                    "Treatment timing could not be resolved well enough to classify the DiD design as canonical or staggered.",
                )
            ]

        if obj.staggered_adoption and estimator in _TWFE_NAMES:
            if obj.heterogeneity_robust_estimator_reported is True:
                return [
                    self._pass(
                        obj,
                        "Staggered adoption is present and a heterogeneity-robust estimator is reported for comparison.",
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
                            "event_study": obj.event_study,
                            "treatment_timing": obj.treatment_timing,
                            "comparison_group": obj.comparison_group,
                            "event_time_window": obj.event_time_window,
                            "fixed_effects": obj.fixed_effects,
                            "clustering": obj.clustering,
                            "method_anchors": (
                                get_method_anchor("did_jel_2026").key,
                                get_method_anchor("did_bjs_2024").key,
                            ),
                        },
                    )
                ]
            return [
                self._unverifiable(
                    obj,
                    "Staggered adoption with TWFE was identified, but the presence of a heterogeneity-robust comparison could not be resolved.",
                )
            ]

        if obj.staggered_adoption or (obj.periods is not None and obj.periods > 2):
            missing = []
            if not obj.treatment_timing:
                missing.append("treatment timing")
            if not obj.comparison_group:
                missing.append("comparison group")
            if obj.event_study is True and obj.event_time_window is None:
                missing.append("event-time window")
            if missing:
                return [
                    self._unverifiable(
                        obj,
                        "Multiple-period DiD design semantics remain incomplete: " + ", ".join(missing) + ".",
                    )
                ]

        return [
            self._pass(
                obj,
                "No currently encoded high-priority DiD design incompatibility was detected from the resolved design semantics.",
            )
        ]

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

    def _review(
        self,
        obj: DIDDesign,
        check_id: str,
        explanation: str,
        evidence: dict[str, object],
    ) -> CheckResult:
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
    """Paper-only weak-IV reporting/inference linting without a hard F cutoff."""

    detector_id = "weak_iv_frontier"
    version = "0.2.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, IVDesign)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, IVDesign)
        normalized = {_normalized(method) for method in obj.weak_robust_methods}
        has_robust = bool(normalized & _WEAK_ROBUST_METHODS)

        if obj.first_stage_reported is False:
            return [
                self._review(
                    obj,
                    "first_stage_missing",
                    "An IV/2SLS design is reported without identified first-stage evidence. This is a reporting and identification-risk flag; it is not proof that the instrument is invalid.",
                    self._design_evidence(obj),
                )
            ]

        if obj.uses_f_gt_10_rule_as_validity_claim:
            evidence = self._design_evidence(obj)
            evidence["reported_first_stage_f"] = obj.first_stage_f.value if obj.first_stage_f else None
            return [
                self._review(
                    obj,
                    "f_gt_10_rule",
                    "The paper treats F > 10 as a validity rule. Veritas does not encode that heuristic as a deterministic validity threshold; weak-IV-robust inference should be examined instead.",
                    evidence,
                )
            ]

        if has_robust:
            return [
                self._pass(
                    obj,
                    "Weak-instrument-robust inference is reported (for example Anderson-Rubin or tF).",
                )
            ]

        single_iv = _resolve_single(obj.single_instrument, obj.instrument_count)
        single_endogenous = _resolve_single(
            obj.single_endogenous_regressor,
            obj.endogenous_regressor_count,
        )
        if single_iv is None or single_endogenous is None:
            return [
                self._unverifiable(
                    obj,
                    "Instrument and endogenous-regressor counts could not be resolved well enough to select the encoded weak-IV check.",
                )
            ]

        if single_iv and single_endogenous:
            if obj.first_stage_f is None:
                return [
                    self._unverifiable(
                        obj,
                        "The just-identified IV structure is resolved, but first-stage strength and weak-IV-robust inference are not sufficiently reported.",
                    )
                ]
            evidence = self._design_evidence(obj)
            evidence.update(
                {
                    "reported_first_stage_f": obj.first_stage_f.value,
                    "no_hard_f_threshold_used": True,
                }
            )
            return [
                self._review(
                    obj,
                    "robust_inference_missing",
                    "A just-identified single-IV result is reported without an encoded weak-IV-robust inference method. "
                    "The reported F statistic is retained as evidence but is not converted into a hard validity cutoff.",
                    evidence,
                )
            ]

        return [
            self._unverifiable(
                obj,
                "The current paper-only weak-IV lint is limited to the single-instrument/single-endogenous-regressor case unless a supported robust inference method is explicitly reported.",
            )
        ]

    def _design_evidence(self, obj: IVDesign) -> dict[str, object]:
        return {
            "instrument_count": obj.instrument_count,
            "endogenous_regressor_count": obj.endogenous_regressor_count,
            "first_stage_reported": obj.first_stage_reported,
            "reduced_form_reported": obj.reduced_form_reported,
            "two_stage_least_squares_reported": obj.two_stage_least_squares_reported,
            "method_anchor": get_method_anchor("weak_iv_jep_2026").key,
        }

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

    def _review(
        self,
        obj: IVDesign,
        check_id: str,
        explanation: str,
        evidence: dict[str, object],
    ) -> CheckResult:
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


def _normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def _resolve_single(explicit: bool | None, count: int | None) -> bool | None:
    if count is not None:
        if count < 1:
            return None
        return count == 1
    return explicit
