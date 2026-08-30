from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import product
from math import sqrt


@dataclass(frozen=True)
class SpecificationConstraint:
    """A pair of choices that may not appear in the same admissible specification."""

    left_dimension: str
    left_choice: str
    right_dimension: str
    right_choice: str
    rationale: str = ""


@dataclass(frozen=True)
class Specification:
    spec_id: str
    choices: tuple[tuple[str, str], ...]
    equivalence_group: str
    rationale: str = ""

    def choice_map(self) -> dict[str, str]:
        return dict(self.choices)


@dataclass(frozen=True)
class SpecificationSpace:
    dimensions: dict[str, tuple[str, ...]]
    constraints: tuple[SpecificationConstraint, ...] = ()
    version: str = "1"

    def enumerate(self) -> tuple[Specification, ...]:
        names = tuple(sorted(self.dimensions))
        options = [self.dimensions[name] for name in names]
        if any(not values for values in options):
            raise ValueError("each specification dimension must contain at least one choice")

        specs: list[Specification] = []
        for combination in product(*options):
            choices = tuple(zip(names, combination, strict=True))
            if not self._is_admissible(dict(choices)):
                continue
            canonical = "|".join(f"{name}={value}" for name, value in choices)
            spec_hash = sha256(canonical.encode()).hexdigest()[:12]
            specs.append(
                Specification(
                    spec_id=f"spec-{spec_hash}",
                    choices=choices,
                    equivalence_group=f"eq-{spec_hash}",
                )
            )
        return tuple(specs)

    def stable_sha256(self) -> str:
        payload = {
            "version": self.version,
            "dimensions": {name: list(values) for name, values in sorted(self.dimensions.items())},
            "constraints": [asdict(constraint) for constraint in self.constraints],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return sha256(raw).hexdigest()

    def _is_admissible(self, choices: dict[str, str]) -> bool:
        for constraint in self.constraints:
            left = choices.get(constraint.left_dimension) == constraint.left_choice
            right = choices.get(constraint.right_dimension) == constraint.right_choice
            if left and right:
                return False
        return True


@dataclass(frozen=True)
class SpecificationEstimate:
    specification: Specification
    estimate: float
    standard_error: float | None = None
    p_value: float | None = None
    original: bool = False


@dataclass(frozen=True)
class SpecificationRobustnessSummary:
    n_specifications: int
    n_equivalence_groups: int
    weighted_median: float
    weighted_q05: float
    weighted_q95: float
    weighted_mean: float
    weighted_sd: float
    sign_stability: float
    practical_effect_stability: float | None
    original_percentile: float | None
    dimension_influence: dict[str, float]


def summarize_specification_robustness(
    estimates: tuple[SpecificationEstimate, ...] | list[SpecificationEstimate],
    *,
    practical_threshold: float | None = None,
) -> SpecificationRobustnessSummary:
    """Summarize a theoretically admissible specification set without p-value vote counting.

    Each equivalence group receives equal total mass, and near-duplicate specifications
    inside a group share that mass. This prevents a researcher from changing the result
    merely by enumerating many cosmetically different variants of one analytic choice.
    """
    if not estimates:
        raise ValueError("at least one specification estimate is required")

    weights = _equivalence_balanced_weights(estimates)
    values = [item.estimate for item in estimates]
    weighted_mean = sum(weight * value for weight, value in zip(weights, values, strict=True))
    weighted_variance = sum(
        weight * (value - weighted_mean) ** 2 for weight, value in zip(weights, values, strict=True)
    )

    original = next((item for item in estimates if item.original), None)
    reference_sign = _sign(original.estimate if original is not None else _weighted_quantile(values, weights, 0.5))
    if reference_sign == 0:
        sign_stability = sum(weight for weight, value in zip(weights, values, strict=True) if _sign(value) == 0)
    else:
        sign_stability = sum(
            weight for weight, value in zip(weights, values, strict=True) if _sign(value) == reference_sign
        )

    practical_stability = None
    if practical_threshold is not None:
        if practical_threshold < 0:
            raise ValueError("practical_threshold must be non-negative")
        practical_stability = sum(
            weight
            for weight, value in zip(weights, values, strict=True)
            if abs(value) >= practical_threshold and (_sign(value) == reference_sign or reference_sign == 0)
        )

    original_percentile = None
    if original is not None:
        original_percentile = sum(
            weight for weight, value in zip(weights, values, strict=True) if value <= original.estimate
        )

    return SpecificationRobustnessSummary(
        n_specifications=len(estimates),
        n_equivalence_groups=len({item.specification.equivalence_group for item in estimates}),
        weighted_median=_weighted_quantile(values, weights, 0.5),
        weighted_q05=_weighted_quantile(values, weights, 0.05),
        weighted_q95=_weighted_quantile(values, weights, 0.95),
        weighted_mean=weighted_mean,
        weighted_sd=sqrt(max(weighted_variance, 0.0)),
        sign_stability=sign_stability,
        practical_effect_stability=practical_stability,
        original_percentile=original_percentile,
        dimension_influence=_dimension_influence(estimates),
    )


def _equivalence_balanced_weights(
    estimates: tuple[SpecificationEstimate, ...] | list[SpecificationEstimate],
) -> list[float]:
    counts = Counter(item.specification.equivalence_group for item in estimates)
    group_count = len(counts)
    return [1.0 / group_count / counts[item.specification.equivalence_group] for item in estimates]


def _weighted_quantile(values: list[float], weights: list[float], quantile: float) -> float:
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be in [0, 1]")
    ordered = sorted(zip(values, weights, strict=True), key=lambda pair: pair[0])
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative + 1e-12 >= quantile:
            return value
    return ordered[-1][0]


def _dimension_influence(
    estimates: tuple[SpecificationEstimate, ...] | list[SpecificationEstimate],
) -> dict[str, float]:
    by_dimension: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for item in estimates:
        for dimension, choice in item.specification.choices:
            by_dimension[dimension][choice].append(item.estimate)

    influence: dict[str, float] = {}
    for dimension, choice_values in by_dimension.items():
        choice_means = [sum(values) / len(values) for values in choice_values.values() if values]
        influence[dimension] = max(choice_means) - min(choice_means) if len(choice_means) > 1 else 0.0
    return dict(sorted(influence.items()))


def _sign(value: float, *, tol: float = 1e-12) -> int:
    if value > tol:
        return 1
    if value < -tol:
        return -1
    return 0
