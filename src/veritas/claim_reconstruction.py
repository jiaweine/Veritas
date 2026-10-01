from __future__ import annotations

import math
from typing import TypeVar

from .claims import ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from .models import RegressionResult, ReportedNumber

_T = TypeVar("_T")
_SUPPORTED_INFERENCE_DISTRIBUTIONS = {"normal", "student_t", "unknown"}


class ClaimObjectReconstructionError(ValueError):
    """Raised when a claim-graph object cannot be reconstructed without guessing."""


def reconstruct_statistical_object(
    graph: StatisticalClaimGraph,
    object_id: str,
) -> object:
    """Reconstruct a typed detector input from graph state only.

    This boundary deliberately does not import parser or ingestion code. Missing
    detector-relevant semantics fail closed instead of falling back to model
    defaults that could accidentally manufacture hard-evidence authority.
    """

    try:
        node = graph.objects[object_id]
    except KeyError as exc:
        raise ClaimObjectReconstructionError(
            f"claim graph has no statistical object {object_id!r}"
        ) from exc

    if node.object_type == "RegressionResult":
        return reconstruct_regression_result(node)
    raise ClaimObjectReconstructionError(
        f"unsupported statistical object type: {node.object_type!r}"
    )


def reconstruct_regression_result(node: StatisticalObjectNode) -> RegressionResult:
    """Rebuild a ``RegressionResult`` without access to the original parser."""

    if node.object_type != "RegressionResult":
        raise ClaimObjectReconstructionError(
            f"expected RegressionResult node, got {node.object_type!r}"
        )

    beta = _reported_number(node, "beta", required=True)
    assert beta is not None
    se = _reported_number(node, "se")
    t_stat = _reported_number(node, "t_stat")
    p_value = _reported_number(node, "p_value")
    ci_lower = _reported_number(node, "ci_lower")
    ci_upper = _reported_number(node, "ci_upper")
    has_ci = ci_lower is not None or ci_upper is not None

    inference_distribution = _string_field(
        node,
        "inference_distribution",
        required=p_value is not None or has_ci,
        default="unknown",
    )
    if inference_distribution not in _SUPPORTED_INFERENCE_DISTRIBUTIONS:
        raise ClaimObjectReconstructionError(
            "inference_distribution must be one of normal, student_t, or unknown"
        )

    degrees_of_freedom = _float_field(node, "degrees_of_freedom")
    ci_level = _float_field(
        node,
        "ci_level",
        required=has_ci,
        default=0.95,
    )
    assert ci_level is not None
    if not 0.0 < ci_level < 1.0:
        raise ClaimObjectReconstructionError("ci_level must be in (0, 1)")

    p_value_adjusted = _bool_field(
        node,
        "p_value_adjusted",
        required=p_value is not None,
        default=False,
    )
    assert p_value_adjusted is not None

    return RegressionResult(
        object_id=node.object_id,
        beta=beta,
        se=se,
        t_stat=t_stat,
        p_value=p_value,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        degrees_of_freedom=degrees_of_freedom,
        inference_distribution=inference_distribution,
        p_value_adjusted=p_value_adjusted,
        source=node.source,
    )


def _reported_number(
    node: StatisticalObjectNode,
    name: str,
    *,
    required: bool = False,
) -> ReportedNumber | None:
    field = _field(node, name, required=required)
    if field is None:
        return None
    value = _finite_number(field, name)
    if field.comparison_operator is None:
        raise ClaimObjectReconstructionError(
            f"field {name!r} is missing an explicit comparison_operator"
        )
    return ReportedNumber(
        value=value,
        decimals=field.displayed_precision,
        operator=field.comparison_operator,
    )


def _float_field(
    node: StatisticalObjectNode,
    name: str,
    *,
    required: bool = False,
    default: float | None = None,
) -> float | None:
    field = _field(node, name, required=required)
    if field is None:
        return default
    return _finite_number(field, name)


def _string_field(
    node: StatisticalObjectNode,
    name: str,
    *,
    required: bool = False,
    default: str | None = None,
) -> str | None:
    field = _field(node, name, required=required)
    if field is None:
        return default
    if not isinstance(field.value, str) or not field.value.strip():
        raise ClaimObjectReconstructionError(f"field {name!r} must contain a non-empty string")
    return field.value.strip()


def _bool_field(
    node: StatisticalObjectNode,
    name: str,
    *,
    required: bool = False,
    default: bool | None = None,
) -> bool | None:
    field = _field(node, name, required=required)
    if field is None:
        return default
    if not isinstance(field.value, bool):
        raise ClaimObjectReconstructionError(f"field {name!r} must contain a boolean")
    return field.value


def _field(
    node: StatisticalObjectNode,
    name: str,
    *,
    required: bool,
) -> ExtractedField | None:
    field = node.fields.get(name)
    if field is None and required:
        raise ClaimObjectReconstructionError(
            f"RegressionResult reconstruction requires field {name!r}"
        )
    return field


def _finite_number(field: ExtractedField, name: str) -> float:
    value = field.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClaimObjectReconstructionError(f"field {name!r} must contain a numeric value")
    number = float(value)
    if not math.isfinite(number):
        raise ClaimObjectReconstructionError(f"field {name!r} must contain a finite value")
    return number
