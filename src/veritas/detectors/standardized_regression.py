from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import cvxpy as cp
import numpy as np
import scs

from ..models import CheckResult, Finding, StandardizedRegressionReconstruction
from ..types import CheckStatus, ComparisonOperator, EvidenceFamily, EvidenceGrade
from .base import Detector

_VALIDATED_SCS_VERSION = "3.2.11"
_BOUND_TOL = 2e-6
_WITNESS_TOL = 2e-5


@dataclass(frozen=True)
class _RelaxationResult:
    status: str  # infeasible | witness | relaxed | unknown
    solver_status: str
    max_exact_residual: float | None = None


class StandardizedRegressionReconstructionDetector(Detector):
    """Reconstruct standardized OLS coefficients from a reported correlation matrix.

    For standardized OLS, the reported quantities must satisfy R_xx beta = r_xy.
    Because both correlations and coefficients are rounded, the equality contains
    bilinear uncertainty. Veritas first attempts a solver-independent constructive
    witness at the midpoint of the correlation intervals. If that fails, each
    R_ij * beta_j term is replaced with a McCormick outer relaxation while the
    candidate correlation matrix is constrained to be PSD.

    Piecewise splitting of beta intervals tightens the relaxation. Only when every
    box covering the reported beta intervals is proven infeasible may the detector
    report an incompatibility. Solver-based incompatibility is capped at E2 until
    AuditBench certification.
    """

    detector_id = "standardized_regression_mccormick_sdp"
    version = "0.3.1"

    def __init__(self, *, max_partition_depth: int = 4, max_nodes: int = 31) -> None:
        if max_partition_depth < 0:
            raise ValueError("max_partition_depth must be non-negative")
        if max_nodes < 1:
            raise ValueError("max_nodes must be positive")
        self.max_partition_depth = max_partition_depth
        self.max_nodes = max_nodes

    def supports(self, obj: object) -> bool:
        return isinstance(obj, StandardizedRegressionReconstruction)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, StandardizedRegressionReconstruction)
        applicability = self._check_applicability(obj)
        if applicability is not None:
            return [applicability]

        prepared = self._prepare_bounds(obj)
        if isinstance(prepared, CheckResult):
            return [prepared]
        correlation_lower, correlation_upper, beta_box = prepared

        midpoint_residual = self._try_midpoint_witness(correlation_lower, correlation_upper, beta_box)
        if midpoint_residual is not None:
            return [
                CheckResult(
                    self.detector_id,
                    "standardized_ols_identity",
                    obj.object_id,
                    CheckStatus.PASS,
                    EvidenceFamily.NUMERICAL_CONSISTENCY,
                    message=(
                        "A solver-independent midpoint correlation matrix is PSD and implies standardized betas "
                        "inside all reported rounding intervals "
                        f"(max identity residual {midpoint_residual:.2e})."
                    ),
                )
            ]

        solver_version = getattr(scs, "__version__", "unknown")
        if solver_version != _VALIDATED_SCS_VERSION:
            return [
                self._unverifiable(
                    obj,
                    "Standardized-regression SDP is disabled because the installed SCS version "
                    f"({solver_version}) differs from the validated version ({_VALIDATED_SCS_VERSION}).",
                )
            ]

        state = {"nodes": 0, "unknown": False, "best_residual": None}
        outcome = self._partition_search(
            correlation_lower,
            correlation_upper,
            beta_box,
            depth=0,
            state=state,
        )

        if outcome == "witness":
            residual = float(state["best_residual"])
            return [
                CheckResult(
                    self.detector_id,
                    "standardized_ols_identity",
                    obj.object_id,
                    CheckStatus.PASS,
                    EvidenceFamily.NUMERICAL_CONSISTENCY,
                    message=(
                        "A PSD correlation matrix and standardized-beta vector within the reported rounding "
                        f"intervals satisfy R_xx beta = r_xy (max residual {residual:.2e})."
                    ),
                )
            ]

        if outcome == "infeasible" and not bool(state["unknown"]):
            explanation = (
                "Even a piecewise McCormick outer relaxation of the reported correlation and standardized-beta "
                "intervals is infeasible under the verified standardized-OLS identity. Because this solver-based "
                "detector is not yet AuditBench-certified, the finding is capped at E2."
            )
            finding = Finding(
                finding_id=f"F-{uuid4().hex[:10]}",
                detector_id=f"{self.detector_id}@{self.version}",
                object_id=obj.object_id,
                grade=EvidenceGrade.METHODOLOGICAL_RISK,
                materiality=obj.materiality,
                family=EvidenceFamily.NUMERICAL_CONSISTENCY,
                title="Standardized regression reconstruction infeasibility",
                explanation=explanation,
                evidence={
                    "outcome": obj.outcome,
                    "predictors": obj.predictors,
                    "beta_intervals": [number.rounding_interval() for number in obj.standardized_betas],
                    "algorithm": "PSD-constrained piecewise McCormick outer relaxation of R_xx beta = r_xy",
                    "partition_depth": self.max_partition_depth,
                    "nodes_checked": state["nodes"],
                    "solver": "SCS",
                    "solver_version": solver_version,
                    "validated_solver_version": _VALIDATED_SCS_VERSION,
                    "severity_ceiling": "E2 until AuditBench certification",
                },
                source=obj.source,
            )
            return [
                CheckResult(
                    self.detector_id,
                    "standardized_ols_identity",
                    obj.object_id,
                    CheckStatus.REVIEW,
                    EvidenceFamily.NUMERICAL_CONSISTENCY,
                    message=explanation,
                    finding=finding,
                )
            ]

        return [
            self._unverifiable(
                obj,
                "The convex outer relaxation remained feasible, but no exact numerical witness was certified "
                "within the configured partition budget; incompatibility cannot be established.",
            )
        ]

    def _check_applicability(self, obj: StandardizedRegressionReconstruction) -> CheckResult | None:
        if not obj.ols_identity_verified:
            return self._unverifiable(obj, "The result is not verified to satisfy the standardized OLS identity.")
        if not obj.same_sample_verified:
            return self._unverifiable(obj, "Correlation and regression results are not verified to use the same sample.")
        if not obj.complete_predictor_set_verified:
            return self._unverifiable(obj, "The correlation matrix is not verified to cover the complete predictor set.")
        if any(number.operator is not ComparisonOperator.EQ for number in obj.standardized_betas):
            return self._unverifiable(obj, "Standardized beta reconstruction requires equality-reported coefficients.")
        return None

    def _prepare_bounds(
        self,
        obj: StandardizedRegressionReconstruction,
    ) -> tuple[np.ndarray, np.ndarray, tuple[tuple[float, float], ...]] | CheckResult:
        matrix = obj.correlation_matrix
        label_to_index = {label: index for index, label in enumerate(matrix.labels)}
        selected = (*obj.predictors, obj.outcome)
        missing = [label for label in selected if label not in label_to_index]
        if missing:
            return self._unverifiable(obj, f"Correlation matrix is missing required variables: {missing}")

        q = len(selected)
        lower = np.eye(q, dtype=float)
        upper = np.eye(q, dtype=float)
        for local_i in range(q):
            for local_j in range(local_i + 1, q):
                source_i = label_to_index[selected[local_i]]
                source_j = label_to_index[selected[local_j]]
                reported = [
                    cell
                    for cell in (matrix.cells[source_i][source_j], matrix.cells[source_j][source_i])
                    if cell is not None
                ]
                if not reported:
                    return self._unverifiable(
                        obj,
                        f"Required correlation {selected[local_i]} / {selected[local_j]} is not reported.",
                    )
                lo = max(-1.0, *(cell.rounding_interval()[0] for cell in reported))
                hi = min(1.0, *(cell.rounding_interval()[1] for cell in reported))
                if lo > hi + _BOUND_TOL:
                    return self._unverifiable(
                        obj,
                        f"Required correlation entries for {selected[local_i]} / {selected[local_j]} conflict.",
                    )
                lower[local_i, local_j] = lower[local_j, local_i] = lo
                upper[local_i, local_j] = upper[local_j, local_i] = hi

        beta_box = tuple(number.rounding_interval() for number in obj.standardized_betas)
        return lower, upper, beta_box

    def _try_midpoint_witness(
        self,
        correlation_lower: np.ndarray,
        correlation_upper: np.ndarray,
        beta_box: tuple[tuple[float, float], ...],
    ) -> float | None:
        matrix = (correlation_lower + correlation_upper) / 2.0
        np.fill_diagonal(matrix, 1.0)
        symmetric = (matrix + matrix.T) / 2.0
        if float(np.min(np.linalg.eigvalsh(symmetric))) < -_WITNESS_TOL:
            return None

        p = len(beta_box)
        r_xx = symmetric[:p, :p]
        r_xy = symmetric[:p, p]
        try:
            beta = np.linalg.solve(r_xx, r_xy)
        except np.linalg.LinAlgError:
            beta, _, _, _ = np.linalg.lstsq(r_xx, r_xy, rcond=None)

        residual = r_xx @ beta - r_xy
        max_residual = float(np.max(np.abs(residual)))
        if max_residual > _WITNESS_TOL:
            return None
        for value, (lo, hi) in zip(beta, beta_box, strict=True):
            if value < lo - _WITNESS_TOL or value > hi + _WITNESS_TOL:
                return None
        return max_residual

    def _partition_search(
        self,
        correlation_lower: np.ndarray,
        correlation_upper: np.ndarray,
        beta_box: tuple[tuple[float, float], ...],
        *,
        depth: int,
        state: dict[str, object],
    ) -> str:
        if int(state["nodes"]) >= self.max_nodes:
            state["unknown"] = True
            return "unknown"
        state["nodes"] = int(state["nodes"]) + 1

        result = self._solve_relaxation(correlation_lower, correlation_upper, beta_box)
        if result.status == "witness":
            state["best_residual"] = result.max_exact_residual
            return "witness"
        if result.status == "infeasible":
            return "infeasible"
        if result.status == "unknown":
            state["unknown"] = True
            return "unknown"

        if depth >= self.max_partition_depth:
            state["unknown"] = True
            return "unknown"

        widths = [hi - lo for lo, hi in beta_box]
        split_index = int(np.argmax(widths))
        if widths[split_index] <= 1e-12:
            state["unknown"] = True
            return "unknown"

        lo, hi = beta_box[split_index]
        midpoint = (lo + hi) / 2.0
        left = list(beta_box)
        right = list(beta_box)
        left[split_index] = (lo, midpoint)
        right[split_index] = (midpoint, hi)

        left_result = self._partition_search(
            correlation_lower,
            correlation_upper,
            tuple(left),
            depth=depth + 1,
            state=state,
        )
        if left_result == "witness":
            return "witness"
        right_result = self._partition_search(
            correlation_lower,
            correlation_upper,
            tuple(right),
            depth=depth + 1,
            state=state,
        )
        if right_result == "witness":
            return "witness"
        if left_result == right_result == "infeasible":
            return "infeasible"
        return "unknown"

    def _solve_relaxation(
        self,
        correlation_lower: np.ndarray,
        correlation_upper: np.ndarray,
        beta_box: tuple[tuple[float, float], ...],
    ) -> _RelaxationResult:
        p = len(beta_box)
        q = p + 1
        matrix = cp.Variable((q, q), symmetric=True)
        beta = cp.Variable(p)
        product = cp.Variable((p, p))

        constraints: list[cp.Constraint] = [cp.diag(matrix) == 1.0, matrix >> 0]
        for i in range(q):
            for j in range(i + 1, q):
                constraints.extend(
                    [
                        matrix[i, j] >= correlation_lower[i, j],
                        matrix[i, j] <= correlation_upper[i, j],
                    ]
                )

        for j, (beta_lo, beta_hi) in enumerate(beta_box):
            constraints.extend([beta[j] >= beta_lo, beta[j] <= beta_hi])

        for i in range(p):
            for j in range(p):
                if i == j:
                    constraints.append(product[i, j] == beta[j])
                    continue
                x = matrix[i, j]
                y = beta[j]
                w = product[i, j]
                x_lo = correlation_lower[i, j]
                x_hi = correlation_upper[i, j]
                y_lo, y_hi = beta_box[j]
                constraints.extend(
                    [
                        w >= x_lo * y + y_lo * x - x_lo * y_lo,
                        w >= x_hi * y + y_hi * x - x_hi * y_hi,
                        w <= x_hi * y + y_lo * x - x_hi * y_lo,
                        w <= x_lo * y + y_hi * x - x_lo * y_hi,
                    ]
                )

        for i in range(p):
            constraints.append(cp.sum(product[i, :]) == matrix[i, p])

        problem = cp.Problem(cp.Minimize(0.0), constraints)
        try:
            problem.solve(solver=cp.SCS, eps=1e-8, max_iters=100_000, verbose=False)
        except cp.error.SolverError:
            return _RelaxationResult("unknown", "solver_error")

        if problem.status == cp.INFEASIBLE:
            return _RelaxationResult("infeasible", problem.status)
        if problem.status != cp.OPTIMAL or matrix.value is None or beta.value is None:
            return _RelaxationResult("unknown", problem.status)

        matrix_value = np.asarray(matrix.value, dtype=float)
        beta_value = np.asarray(beta.value, dtype=float)
        residual = matrix_value[:p, :p] @ beta_value - matrix_value[:p, p]
        max_residual = float(np.max(np.abs(residual)))
        if self._verify_exact_witness(
            matrix_value,
            beta_value,
            correlation_lower,
            correlation_upper,
            beta_box,
            max_residual,
        ):
            return _RelaxationResult("witness", problem.status, max_exact_residual=max_residual)
        return _RelaxationResult("relaxed", problem.status, max_exact_residual=max_residual)

    def _verify_exact_witness(
        self,
        matrix: np.ndarray,
        beta: np.ndarray,
        correlation_lower: np.ndarray,
        correlation_upper: np.ndarray,
        beta_box: tuple[tuple[float, float], ...],
        max_residual: float,
    ) -> bool:
        if max_residual > _WITNESS_TOL:
            return False
        symmetric = (matrix + matrix.T) / 2.0
        if float(np.min(np.linalg.eigvalsh(symmetric))) < -_WITNESS_TOL:
            return False
        if float(np.max(np.abs(np.diag(symmetric) - 1.0))) > _WITNESS_TOL:
            return False
        q = matrix.shape[0]
        for i in range(q):
            for j in range(i + 1, q):
                value = symmetric[i, j]
                if value < correlation_lower[i, j] - _WITNESS_TOL:
                    return False
                if value > correlation_upper[i, j] + _WITNESS_TOL:
                    return False
        for value, (lo, hi) in zip(beta, beta_box, strict=True):
            if value < lo - _WITNESS_TOL or value > hi + _WITNESS_TOL:
                return False
        return True

    def _unverifiable(self, obj: StandardizedRegressionReconstruction, message: str) -> CheckResult:
        return CheckResult(
            self.detector_id,
            "standardized_ols_identity",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.NUMERICAL_CONSISTENCY,
            message=message,
        )
