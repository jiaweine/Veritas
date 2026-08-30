from __future__ import annotations

from math import exp
from uuid import uuid4

from ..models import CheckResult, Finding, LogitResult, MediationResult
from ..types import CheckStatus, EvidenceFamily, EvidenceGrade
from .base import Detector

_EPS = 1e-12


def _intersects(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return max(left[0], right[0]) <= min(left[1], right[1]) + _EPS


def _product_interval(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float]:
    values = [a * b for a in left for b in right]
    return min(values), max(values)


class LogitOddsRatioDetector(Detector):
    detector_id = "logit_odds_ratio_consistency"
    version = "0.3.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, LogitResult)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, LogitResult)
        if not obj.exp_beta_relation_verified:
            return [self._unverifiable(obj, "The reported odds ratio has not been verified as exp(beta) on the same scale.")]

        beta_lo, beta_hi = obj.beta.rounding_interval()
        possible_or = (exp(beta_lo), exp(beta_hi))
        reported_or = obj.odds_ratio.rounding_interval()
        if reported_or[1] <= 0:
            return [self._failure(obj, possible_or, reported_or, "Reported odds ratio is non-positive.")]
        if _intersects(possible_or, reported_or):
            return [
                CheckResult(
                    self.detector_id,
                    "exp_beta",
                    obj.object_id,
                    CheckStatus.PASS,
                    EvidenceFamily.NUMERICAL_CONSISTENCY,
                    message="Reported beta and odds ratio are compatible after accounting for rounding.",
                )
            ]
        return [
            self._failure(
                obj,
                possible_or,
                reported_or,
                "Reported odds ratio is incompatible with exp(beta) after accounting for rounding.",
            )
        ]

    def _failure(
        self,
        obj: LogitResult,
        possible_or: tuple[float, float],
        reported_or: tuple[float, float],
        explanation: str,
    ) -> CheckResult:
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.INTERNAL_CONTRADICTION,
            materiality=obj.materiality,
            family=EvidenceFamily.NUMERICAL_CONSISTENCY,
            title="Logit / odds-ratio reporting contradiction",
            explanation=explanation,
            evidence={
                "reported_beta_interval": obj.beta.rounding_interval(),
                "possible_exp_beta_interval": possible_or,
                "reported_odds_ratio_interval": reported_or,
            },
            source=obj.source,
        )
        return CheckResult(
            self.detector_id,
            "exp_beta",
            obj.object_id,
            CheckStatus.FAIL,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=explanation,
            finding=finding,
        )

    def _unverifiable(self, obj: LogitResult, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "exp_beta",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )


class MediationProductDetector(Detector):
    detector_id = "mediation_product_consistency"
    version = "0.3.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, MediationResult)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, MediationResult)
        if not obj.product_definition_verified:
            return [self._unverifiable(obj, "The indirect effect has not been verified as the product a*b.")]
        if not obj.scale_consistent_verified:
            return [self._unverifiable(obj, "The a, b, and indirect effects are not verified to use compatible scales.")]

        possible = _product_interval(obj.a_path.rounding_interval(), obj.b_path.rounding_interval())
        reported = obj.indirect_effect.rounding_interval()
        if _intersects(possible, reported):
            return [
                CheckResult(
                    self.detector_id,
                    "a_times_b",
                    obj.object_id,
                    CheckStatus.PASS,
                    EvidenceFamily.NUMERICAL_CONSISTENCY,
                    message="Reported indirect effect is compatible with a*b after accounting for rounding.",
                )
            ]

        explanation = "Reported indirect effect is incompatible with a*b after accounting for rounding."
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.INTERNAL_CONTRADICTION,
            materiality=obj.materiality,
            family=EvidenceFamily.NUMERICAL_CONSISTENCY,
            title="Mediation reporting contradiction",
            explanation=explanation,
            evidence={
                "a_interval": obj.a_path.rounding_interval(),
                "b_interval": obj.b_path.rounding_interval(),
                "possible_indirect_interval": possible,
                "reported_indirect_interval": reported,
            },
            source=obj.source,
        )
        return [
            CheckResult(
                self.detector_id,
                "a_times_b",
                obj.object_id,
                CheckStatus.FAIL,
                EvidenceFamily.NUMERICAL_CONSISTENCY,
                message=explanation,
                finding=finding,
            )
        ]

    def _unverifiable(self, obj: MediationResult, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "a_times_b",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )
