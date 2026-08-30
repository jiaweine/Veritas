from __future__ import annotations

from uuid import uuid4

import cvxpy as cp
import numpy as np

from ..models import CheckResult, CorrelationMatrix, Finding, ReportedNumber
from ..types import CheckStatus, EvidenceFamily, EvidenceGrade
from .base import Detector

_NUMERICAL_TOL = 1e-7
_HARD_MARGIN = 1e-4


def _interval(number: ReportedNumber) -> tuple[float, float]:
    return number.rounding_interval()


def _intersection(intervals: list[tuple[float, float]]) -> tuple[float, float] | None:
    lo = max(interval[0] for interval in intervals)
    hi = min(interval[1] for interval in intervals)
    if lo > hi + _NUMERICAL_TOL:
        return None
    return lo, hi


class CorrelationPSDDetector(Detector):
    """Check whether any PSD correlation matrix is compatible with displayed rounding.

    The detector maximizes the smallest eigenvalue over all matrices inside the
    reported cell intervals. A non-negative optimum means at least one legal
    correlation matrix is compatible with the paper. A negative optimum means
    no PSD completion exists under the modeled rounding intervals.

    SDP-based negative margins are deliberately capped at E2 while this detector
    is experimental; direct algebraic contradictions can be E3.
    """

    detector_id = "correlation_psd_sdp"
    version = "0.1.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, CorrelationMatrix)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, CorrelationMatrix)
        bounds_or_failure = self._build_bounds(obj)
        if isinstance(bounds_or_failure, CheckResult):
            return [bounds_or_failure]
        lower, upper = bounds_or_failure

        n = len(obj.labels)
        matrix = cp.Variable((n, n), symmetric=True)
        margin = cp.Variable()
        constraints: list[cp.Constraint] = [cp.diag(matrix) == 1.0, matrix - margin * np.eye(n) >> 0]
        for i in range(n):
            for j in range(i + 1, n):
                constraints.extend([matrix[i, j] >= lower[i, j], matrix[i, j] <= upper[i, j]])

        problem = cp.Problem(cp.Maximize(margin), constraints)
        try:
            problem.solve(solver=cp.SCS, eps=1e-8, max_iters=100_000, verbose=False)
        except cp.error.SolverError as exc:
            return [self._unverifiable(obj, f"SDP solver failed: {exc}")]

        if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} or margin.value is None:
            return [self._unverifiable(obj, f"SDP did not return a usable optimum: {problem.status}")]

        optimum = float(margin.value)
        evidence = {
            "max_compatible_min_eigenvalue": optimum,
            "solver": "SCS",
            "solver_status": problem.status,
            "variables": list(obj.labels),
            "algorithm": "rounding-interval semidefinite max-min eigenvalue feasibility",
        }
        if optimum >= -_NUMERICAL_TOL:
            return [
                CheckResult(
                    self.detector_id,
                    "psd_feasibility",
                    obj.object_id,
                    CheckStatus.PASS,
                    EvidenceFamily.NUMERICAL_CONSISTENCY,
                    message="At least one PSD correlation matrix is compatible with the reported rounding intervals.",
                )
            ]

        explanation = (
            "No positive-semidefinite correlation matrix was found within all reported rounding intervals. "
            "Because the SDP detector is not yet AuditBench-certified, this remains a methodological review signal, "
            "not a hard contradiction."
        )
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.METHODOLOGICAL_RISK,
            materiality=obj.materiality,
            family=EvidenceFamily.NUMERICAL_CONSISTENCY,
            title="Correlation-matrix feasibility concern",
            explanation=explanation,
            evidence={**evidence, "hard_margin_threshold": -_HARD_MARGIN},
            detector_precision=0.5,
            source=obj.source,
        )
        return [
            CheckResult(
                self.detector_id,
                "psd_feasibility",
                obj.object_id,
                CheckStatus.REVIEW,
                EvidenceFamily.NUMERICAL_CONSISTENCY,
                message=explanation,
                finding=finding,
            )
        ]

    def _build_bounds(self, obj: CorrelationMatrix) -> tuple[np.ndarray, np.ndarray] | CheckResult:
        n = len(obj.labels)
        lower = np.full((n, n), -1.0, dtype=float)
        upper = np.full((n, n), 1.0, dtype=float)
        np.fill_diagonal(lower, 1.0)
        np.fill_diagonal(upper, 1.0)

        for i in range(n):
            diagonal = obj.cells[i][i]
            if diagonal is not None:
                lo, hi = _interval(diagonal)
                if not (lo - _NUMERICAL_TOL <= 1.0 <= hi + _NUMERICAL_TOL):
                    return self._direct_contradiction(
                        obj,
                        "diagonal",
                        "A reported correlation-matrix diagonal entry is incompatible with 1.",
                        {"variable": obj.labels[i], "reported_interval": (lo, hi)},
                    )

            for j in range(i + 1, n):
                reported = [cell for cell in (obj.cells[i][j], obj.cells[j][i]) if cell is not None]
                if not reported:
                    continue
                intervals = [_interval(cell) for cell in reported]
                intervals.append((-1.0, 1.0))
                overlap = _intersection(intervals)
                if overlap is None:
                    return self._direct_contradiction(
                        obj,
                        "cell_bounds",
                        "Reported correlation entries cannot be reconciled with symmetry and the [-1, 1] range.",
                        {
                            "variables": (obj.labels[i], obj.labels[j]),
                            "reported_intervals": intervals[:-1],
                        },
                    )
                lo, hi = overlap
                lower[i, j] = lower[j, i] = lo
                upper[i, j] = upper[j, i] = hi
        return lower, upper

    def _unverifiable(self, obj: CorrelationMatrix, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "psd_feasibility",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )

    def _direct_contradiction(
        self,
        obj: CorrelationMatrix,
        check_id: str,
        explanation: str,
        evidence: dict[str, object],
    ) -> CheckResult:
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.INTERNAL_CONTRADICTION,
            materiality=obj.materiality,
            family=EvidenceFamily.NUMERICAL_CONSISTENCY,
            title="Correlation reporting contradiction",
            explanation=explanation,
            evidence=evidence,
            source=obj.source,
        )
        return CheckResult(
            self.detector_id,
            check_id,
            obj.object_id,
            CheckStatus.FAIL,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=explanation,
            finding=finding,
        )
