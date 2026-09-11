from __future__ import annotations

from uuid import uuid4

from ..methodology import get_method_anchor
from ..models import CheckResult, Finding, RDDDesign
from ..types import CheckStatus, EvidenceFamily, EvidenceGrade
from .base import Detector


class RDDDesignDetector(Detector):
    detector_id = "rdd_design_frontier"
    version = "0.1.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, RDDDesign)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, RDDDesign)

        if obj.global_polynomial_order is not None and obj.global_polynomial_order >= 3:
            return [
                self._review(
                    obj,
                    "global_high_order_polynomial",
                    "High-order global polynomials are not recommended for RD estimation/inference near the cutoff; "
                    "modern practice favors local-polynomial methods with explicit bandwidth and robust inference.",
                    {
                        "global_polynomial_order": obj.global_polynomial_order,
                        "method_anchor": get_method_anchor("rdd_extensions_2024").key,
                    },
                )
            ]

        if obj.framework == "continuity":
            if obj.robust_bias_corrected_inference is True or obj.alternative_modern_inference_reported is True:
                return [self._pass(obj, "Modern continuity-based RD inference is reported.")]
            if obj.robust_bias_corrected_inference is False and obj.alternative_modern_inference_reported is False:
                return [
                    self._review(
                        obj,
                        "continuity_inference",
                        "Continuity-based RD is reported without robust bias-corrected or another explicitly modern "
                        "inference procedure. This is an inference-risk flag, not evidence of misconduct.",
                        {
                            "method_anchor": get_method_anchor("rdd_extensions_2024").key,
                            "bandwidth_selection": obj.bandwidth_selection,
                            "density_test_reported": obj.density_test_reported,
                        },
                    )
                ]
            return [self._unverifiable(obj, "The RD inference procedure could not be resolved from available material.")]

        if obj.framework == "local_randomization":
            if obj.randomization_inference_reported is True:
                return [self._pass(obj, "Local-randomization RD reports randomization-based inference.")]
            if obj.randomization_inference_reported is False:
                return [
                    self._review(
                        obj,
                        "local_randomization_inference",
                        "The paper frames the RD as local randomization but no randomization-based inference was identified.",
                        {"method_anchor": get_method_anchor("rdd_extensions_2024").key},
                    )
                ]
            return [self._unverifiable(obj, "Local-randomization inference could not be resolved.")]

        return [self._unverifiable(obj, "RD framework could not be classified as continuity or local randomization.")]

    def _pass(self, obj: RDDDesign, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "design_compatibility",
            obj.object_id,
            CheckStatus.PASS,
            EvidenceFamily.DESIGN_VALIDITY,
            message=message,
        )

    def _unverifiable(self, obj: RDDDesign, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "design_compatibility",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.DESIGN_VALIDITY,
            message=message,
        )

    def _review(self, obj: RDDDesign, check_id: str, explanation: str, evidence: dict[str, object]) -> CheckResult:
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.METHODOLOGICAL_RISK,
            materiality=obj.materiality,
            family=EvidenceFamily.DESIGN_VALIDITY,
            title="Regression-discontinuity design risk",
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
