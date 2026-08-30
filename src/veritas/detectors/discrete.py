from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from math import isfinite
from uuid import uuid4

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from ..models import CheckResult, DiscreteSummary, Finding, ReportedNumber
from ..types import CheckStatus, ComparisonOperator, EvidenceFamily, EvidenceGrade
from .base import Detector


@dataclass(frozen=True)
class _FeasibilityOutcome:
    status: str  # feasible | infeasible | unknown
    witness: dict[float, int] | None = None
    reason: str = ""
    candidate_sums: int = 0


def _decimal_interval(value: ReportedNumber) -> tuple[Decimal, Decimal]:
    center = Decimal(str(value.value))
    if value.decimals is None:
        return center, center
    unit = Decimal(1).scaleb(-value.decimals)
    half = unit / Decimal(2)
    return center - half, center + half


def _ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _floor_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _integerize_support(support: tuple[float, ...], *, max_decimal_places: int) -> tuple[tuple[int, ...], int]:
    values = [Decimal(str(value)) for value in support]
    places = max(0, max(-value.as_tuple().exponent for value in values))
    if places > max_decimal_places:
        raise ValueError(
            f"support requires {places} decimal places; configured maximum is {max_decimal_places}"
        )
    scale = 10**places
    integers = tuple(int(value * scale) for value in values)
    if len(set(integers)) != len(integers):
        raise ValueError("support values collapse to duplicates after integer scaling")
    return integers, scale


def _verified_witness(
    counts: np.ndarray,
    support_int: tuple[int, ...],
    n: int,
    sum_bounds: tuple[int, int],
    q_bounds: tuple[int, int] | None,
) -> tuple[int, ...] | None:
    rounded = tuple(round(value) for value in counts)
    if any(value < 0 for value in rounded) or sum(rounded) != n:
        return None
    total = sum(value * count for value, count in zip(support_int, rounded, strict=True))
    if not sum_bounds[0] <= total <= sum_bounds[1]:
        return None
    if q_bounds is not None:
        total_q = sum(value * value * count for value, count in zip(support_int, rounded, strict=True))
        if not q_bounds[0] <= total_q <= q_bounds[1]:
            return None
    return rounded


class DiscreteSummaryFeasibilityDetector(Detector):
    """Generalized GRIM/GRIMMER-style feasibility over an explicit finite support.

    The detector asks whether any integer histogram can reproduce the reported N,
    rounded mean and, when available, rounded SD. Infeasibility is currently capped
    at E2 until this detector is certified on the locked AuditBench test split.
    """

    detector_id = "discrete_summary_feasibility"
    version = "0.3.0"

    def __init__(
        self,
        *,
        max_sum_candidates: int = 512,
        max_decimal_places: int = 6,
        per_solve_time_limit: float = 1.0,
    ) -> None:
        self.max_sum_candidates = max_sum_candidates
        self.max_decimal_places = max_decimal_places
        self.per_solve_time_limit = per_solve_time_limit

    def supports(self, obj: object) -> bool:
        return isinstance(obj, DiscreteSummary)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, DiscreteSummary)
        applicability = self._check_applicability(obj)
        if applicability is not None:
            return [applicability]

        try:
            outcome = self._solve(obj)
        except (ValueError, OverflowError) as exc:
            return [self._unverifiable(obj, str(exc))]

        if outcome.status == "feasible":
            return [
                CheckResult(
                    self.detector_id,
                    "finite_support_feasibility",
                    obj.object_id,
                    CheckStatus.PASS,
                    EvidenceFamily.NUMERICAL_CONSISTENCY,
                    message="A discrete sample compatible with the reported summaries exists.",
                )
            ]
        if outcome.status == "unknown":
            return [self._unverifiable(obj, outcome.reason)]

        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.METHODOLOGICAL_RISK,
            materiality=obj.materiality,
            family=EvidenceFamily.NUMERICAL_CONSISTENCY,
            title="Discrete summary infeasibility",
            explanation=(
                "No integer-valued sample on the verified support can reproduce the reported N, "
                "mean and optional SD within their rounding-compatible intervals. The finding is "
                "capped at E2 until AuditBench hard-alert certification."
            ),
            evidence={
                "n": obj.n,
                "support": obj.support,
                "reported_mean": obj.mean.value,
                "reported_sd": obj.sd.value if obj.sd is not None else None,
                "sd_definition": obj.sd_definition,
                "candidate_sums_checked": outcome.candidate_sums,
                "solver": "scipy.optimize.milp (HiGHS)",
                "severity_ceiling": "E2 until AuditBench certification",
            },
            source=obj.source,
        )
        return [
            CheckResult(
                self.detector_id,
                "finite_support_feasibility",
                obj.object_id,
                CheckStatus.FAIL,
                EvidenceFamily.NUMERICAL_CONSISTENCY,
                message=finding.explanation,
                finding=finding,
            )
        ]

    def _check_applicability(self, obj: DiscreteSummary) -> CheckResult | None:
        if not obj.support_verified:
            return self._unverifiable(obj, "The variable's finite support has not been independently verified.")
        if not obj.n_verified:
            return self._unverifiable(obj, "The reported N has not been verified as specific to this statistic.")
        if obj.weighted is not False:
            return self._unverifiable(obj, "Weighted or unknown-weight summaries are not finite-count histograms.")
        if obj.mean.operator is not ComparisonOperator.EQ:
            return self._unverifiable(obj, "Mean feasibility currently requires an equality-reported mean.")
        if obj.sd is not None and obj.sd.operator is not ComparisonOperator.EQ:
            return self._unverifiable(obj, "SD feasibility currently requires an equality-reported SD.")
        if obj.sd is not None and obj.sd_definition not in {"sample", "population"}:
            return self._unverifiable(obj, "The SD definition must be known as sample or population.")
        return None

    def _solve(self, obj: DiscreteSummary) -> _FeasibilityOutcome:
        if obj.n <= 0:
            raise ValueError("N must be positive")
        if any(not isfinite(value) for value in obj.support):
            raise ValueError("support values must be finite")

        support_int, scale = _integerize_support(
            obj.support,
            max_decimal_places=self.max_decimal_places,
        )
        mean_lo, mean_hi = _decimal_interval(obj.mean)
        scaled_n = Decimal(obj.n * scale)
        sum_lo = _ceil_decimal(mean_lo * scaled_n)
        sum_hi = _floor_decimal(mean_hi * scaled_n)

        theoretical_lo = obj.n * min(support_int)
        theoretical_hi = obj.n * max(support_int)
        sum_lo = max(sum_lo, theoretical_lo)
        sum_hi = min(sum_hi, theoretical_hi)
        if sum_lo > sum_hi:
            return _FeasibilityOutcome("infeasible", candidate_sums=0)

        if obj.sd is None:
            return self._solve_mean_only(obj, support_int, sum_lo, sum_hi)
        return self._solve_mean_sd(obj, support_int, scale, sum_lo, sum_hi)

    def _solve_mean_only(
        self,
        obj: DiscreteSummary,
        support_int: tuple[int, ...],
        sum_lo: int,
        sum_hi: int,
    ) -> _FeasibilityOutcome:
        matrix = np.vstack([np.ones(len(support_int)), np.asarray(support_int, dtype=float)])
        result = self._milp(
            obj.n,
            matrix,
            np.asarray([obj.n, sum_lo], dtype=float),
            np.asarray([obj.n, sum_hi], dtype=float),
        )
        if result.status == 2:
            return _FeasibilityOutcome("infeasible", candidate_sums=sum_hi - sum_lo + 1)
        if not result.success or result.x is None:
            return _FeasibilityOutcome("unknown", reason=f"MILP solver status {result.status}: {result.message}")

        witness = _verified_witness(result.x, support_int, obj.n, (sum_lo, sum_hi), None)
        if witness is None:
            return _FeasibilityOutcome("unknown", reason="MILP returned a witness that failed integer re-verification.")
        return _FeasibilityOutcome(
            "feasible",
            witness=dict(zip(obj.support, witness, strict=True)),
            candidate_sums=sum_hi - sum_lo + 1,
        )

    def _solve_mean_sd(
        self,
        obj: DiscreteSummary,
        support_int: tuple[int, ...],
        scale: int,
        sum_lo: int,
        sum_hi: int,
    ) -> _FeasibilityOutcome:
        assert obj.sd is not None
        if obj.sd_definition == "sample" and obj.n < 2:
            return _FeasibilityOutcome("unknown", reason="Sample SD is undefined for N < 2.")

        candidate_count = sum_hi - sum_lo + 1
        if candidate_count > self.max_sum_candidates:
            return _FeasibilityOutcome(
                "unknown",
                reason=(
                    f"Mean rounding interval permits {candidate_count} integer sums, exceeding the "
                    f"configured exact-search budget of {self.max_sum_candidates}."
                ),
                candidate_sums=candidate_count,
            )

        sd_lo, sd_hi = _decimal_interval(obj.sd)
        sd_lo = max(sd_lo, Decimal(0))
        if sd_hi < 0:
            return _FeasibilityOutcome("infeasible", candidate_sums=candidate_count)

        denominator = obj.n - 1 if obj.sd_definition == "sample" else obj.n
        scale_sq = Decimal(scale * scale)
        unknown_seen = False
        support_array = np.asarray(support_int, dtype=float)
        matrix = np.vstack([np.ones(len(support_int)), support_array, support_array**2])

        for total_sum in range(sum_lo, sum_hi + 1):
            center_term = Decimal(total_sum * total_sum) / Decimal(obj.n)
            q_lo_dec = Decimal(denominator) * sd_lo * sd_lo * scale_sq + center_term
            q_hi_dec = Decimal(denominator) * sd_hi * sd_hi * scale_sq + center_term
            q_lo = _ceil_decimal(q_lo_dec)
            q_hi = _floor_decimal(q_hi_dec)
            if q_lo > q_hi:
                continue

            result = self._milp(
                obj.n,
                matrix,
                np.asarray([obj.n, total_sum, q_lo], dtype=float),
                np.asarray([obj.n, total_sum, q_hi], dtype=float),
            )
            if result.success and result.x is not None:
                witness = _verified_witness(
                    result.x,
                    support_int,
                    obj.n,
                    (total_sum, total_sum),
                    (q_lo, q_hi),
                )
                if witness is None:
                    unknown_seen = True
                    continue
                return _FeasibilityOutcome(
                    "feasible",
                    witness=dict(zip(obj.support, witness, strict=True)),
                    candidate_sums=candidate_count,
                )
            if result.status != 2:
                unknown_seen = True

        if unknown_seen:
            return _FeasibilityOutcome(
                "unknown",
                reason="At least one candidate sum could not be conclusively solved by the MILP backend.",
                candidate_sums=candidate_count,
            )
        return _FeasibilityOutcome("infeasible", candidate_sums=candidate_count)

    def _milp(
        self,
        n: int,
        matrix: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
    ):
        variable_count = matrix.shape[1]
        return milp(
            c=np.zeros(variable_count),
            integrality=np.ones(variable_count),
            bounds=Bounds(np.zeros(variable_count), np.full(variable_count, n, dtype=float)),
            constraints=LinearConstraint(matrix, lower, upper),
            options={"time_limit": self.per_solve_time_limit, "presolve": True},
        )

    def _unverifiable(self, obj: DiscreteSummary, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "finite_support_feasibility",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )
