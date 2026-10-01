from __future__ import annotations

import math

from .claims import ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from .group_stats import GroupSummary, TwoGroupComparison
from .models import CorrelationMatrix, RegressionResult, ReportedNumber, SamplePartition

_SUPPORTED_INFERENCE_DISTRIBUTIONS = {"normal", "student_t", "unknown"}
_SUPPORTED_SD_DEFINITIONS = {"sample", "population", "unknown"}
_SUPPORTED_TWO_GROUP_TESTS = {"student_equal_var", "welch", "unknown"}
_SUPPORTED_HEDGES_CORRECTIONS = {"exact_gamma", "approx_4df_minus_1", "unknown"}
_GROUP_COUNT_PREFIX = "group_count:"
_LABEL_PREFIX = "label:"
_CELL_PREFIX = "cell:"


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
    if node.object_type == "SamplePartition":
        return reconstruct_sample_partition(node)
    if node.object_type == "CorrelationMatrix":
        return reconstruct_correlation_matrix(node)
    if node.object_type == "MeanSD":
        return reconstruct_mean_sd(node)
    if node.object_type == "GroupComparison":
        return reconstruct_group_comparison(node)
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


def reconstruct_sample_partition(node: StatisticalObjectNode) -> SamplePartition:
    """Rebuild a sample partition from individually source-addressable counts."""

    if node.object_type != "SamplePartition":
        raise ClaimObjectReconstructionError(
            f"expected SamplePartition node, got {node.object_type!r}"
        )

    total_n = _int_field(node, "total_n")
    if total_n is not None and total_n < 0:
        raise ClaimObjectReconstructionError("total_n must be non-negative")

    groups: dict[str, int] = {}
    for field_name, field in node.fields.items():
        if not field_name.startswith(_GROUP_COUNT_PREFIX):
            continue
        label = field_name[len(_GROUP_COUNT_PREFIX) :]
        if not label.strip():
            raise ClaimObjectReconstructionError("group_count field requires a non-empty label")
        count = _integer_value(field, field_name)
        if count < 0:
            raise ClaimObjectReconstructionError(f"field {field_name!r} must be non-negative")
        groups[label] = count

    non_overlapping = _bool_field(
        node,
        "non_overlapping",
        required=bool(groups),
        default=True,
    )
    assert non_overlapping is not None
    exhaustive = _bool_field(node, "exhaustive")
    explanation_present = _bool_field(node, "explanation_present")

    return SamplePartition(
        object_id=node.object_id,
        total_n=total_n,
        groups=groups,
        exhaustive=exhaustive,
        non_overlapping=non_overlapping,
        explanation_present=explanation_present,
        source=node.source,
    )


def reconstruct_correlation_matrix(node: StatisticalObjectNode) -> CorrelationMatrix:
    """Rebuild a correlation matrix from indexed label/cell graph fields.

    Labels use ``label:<index>`` and cells use ``cell:<row>:<column>``. Every
    numerical cell remains its own ``ExtractedField`` and therefore retains its
    source location, raw display string, rounding precision, operator, and
    extraction/identity confidence in the graph.
    """

    if node.object_type != "CorrelationMatrix":
        raise ClaimObjectReconstructionError(
            f"expected CorrelationMatrix node, got {node.object_type!r}"
        )

    labels_by_index: dict[int, str] = {}
    for field_name, field in node.fields.items():
        if not field_name.startswith(_LABEL_PREFIX):
            continue
        index = _single_index(field_name, _LABEL_PREFIX)
        if index in labels_by_index:
            raise ClaimObjectReconstructionError(f"duplicate correlation label index {index}")
        if not isinstance(field.value, str) or not field.value.strip():
            raise ClaimObjectReconstructionError(
                f"field {field_name!r} must contain a non-empty label"
            )
        labels_by_index[index] = field.value.strip()

    if len(labels_by_index) < 2:
        raise ClaimObjectReconstructionError("CorrelationMatrix requires at least two label fields")
    expected_indexes = set(range(len(labels_by_index)))
    if set(labels_by_index) != expected_indexes:
        raise ClaimObjectReconstructionError(
            "correlation label indexes must be contiguous and start at zero"
        )
    labels = tuple(labels_by_index[index] for index in range(len(labels_by_index)))
    if len(set(labels)) != len(labels):
        raise ClaimObjectReconstructionError("correlation labels must be unique")

    size = len(labels)
    cells: list[list[ReportedNumber | None]] = [[None for _ in range(size)] for _ in range(size)]
    for field_name, field in node.fields.items():
        if not field_name.startswith(_CELL_PREFIX):
            continue
        row, column = _matrix_indexes(field_name)
        if row >= size or column >= size:
            raise ClaimObjectReconstructionError(
                f"correlation cell {field_name!r} references label index outside matrix"
            )
        cells[row][column] = _reported_from_field(field, field_name)

    return CorrelationMatrix(
        object_id=node.object_id,
        labels=labels,
        cells=tuple(tuple(row) for row in cells),
        source=node.source,
    )


def reconstruct_mean_sd(node: StatisticalObjectNode) -> GroupSummary:
    """Rebuild one N/mean/SD summary while preserving fail-closed semantics."""

    if node.object_type != "MeanSD":
        raise ClaimObjectReconstructionError(f"expected MeanSD node, got {node.object_type!r}")
    return _group_summary(node, "")


def reconstruct_group_comparison(node: StatisticalObjectNode) -> TwoGroupComparison:
    """Rebuild a two-group detector input from scalar source-addressable fields."""

    if node.object_type != "GroupComparison":
        raise ClaimObjectReconstructionError(
            f"expected GroupComparison node, got {node.object_type!r}"
        )

    group_a = _group_summary(node, "group_a:")
    group_b = _group_summary(node, "group_b:")
    if group_a.label == group_b.label:
        raise ClaimObjectReconstructionError("group comparison labels must be distinct")

    reported_p_value = _reported_number(node, "reported_p_value")
    test_definition = _string_field(node, "test_definition", default="unknown")
    if test_definition not in _SUPPORTED_TWO_GROUP_TESTS:
        raise ClaimObjectReconstructionError(
            "test_definition must be student_equal_var, welch, or unknown"
        )
    hedges_correction = _string_field(node, "hedges_correction", default="unknown")
    if hedges_correction not in _SUPPORTED_HEDGES_CORRECTIONS:
        raise ClaimObjectReconstructionError(
            "hedges_correction must be exact_gamma, approx_4df_minus_1, or unknown"
        )

    p_value_adjusted = _bool_field(
        node,
        "p_value_adjusted",
        required=reported_p_value is not None,
        default=False,
    )
    assert p_value_adjusted is not None

    return TwoGroupComparison(
        object_id=node.object_id,
        group_a=group_a,
        group_b=group_b,
        reported_mean_difference=_reported_number(node, "reported_mean_difference"),
        reported_t=_reported_number(node, "reported_t"),
        reported_df=_reported_number(node, "reported_df"),
        reported_p_value=reported_p_value,
        reported_cohen_d=_reported_number(node, "reported_cohen_d"),
        reported_hedges_g=_reported_number(node, "reported_hedges_g"),
        test_definition=test_definition,
        hedges_correction=hedges_correction,
        independent_groups_verified=bool(
            _bool_field(node, "independent_groups_verified", default=False)
        ),
        same_outcome_scale_verified=bool(
            _bool_field(node, "same_outcome_scale_verified", default=False)
        ),
        difference_direction_verified=bool(
            _bool_field(node, "difference_direction_verified", default=False)
        ),
        pooled_sd_effect_size_verified=bool(
            _bool_field(node, "pooled_sd_effect_size_verified", default=False)
        ),
        p_value_adjusted=p_value_adjusted,
        source=node.source,
    )


def _group_summary(node: StatisticalObjectNode, prefix: str) -> GroupSummary:
    label_name = f"{prefix}label"
    n_name = f"{prefix}n"
    mean_name = f"{prefix}mean"
    sd_name = f"{prefix}sd"
    sd_definition_name = f"{prefix}sd_definition"
    weighted_name = f"{prefix}weighted"

    label = _string_field(node, label_name, required=True)
    n = _int_field(node, n_name, required=True)
    mean = _reported_number(node, mean_name, required=True)
    sd = _reported_number(node, sd_name, required=True)
    assert label is not None and n is not None and mean is not None and sd is not None

    if n < 2:
        raise ClaimObjectReconstructionError(f"field {n_name!r} must be at least 2")
    if sd.value < 0:
        raise ClaimObjectReconstructionError(f"field {sd_name!r} must be non-negative")

    sd_definition = _string_field(node, sd_definition_name, default="unknown")
    if sd_definition not in _SUPPORTED_SD_DEFINITIONS:
        raise ClaimObjectReconstructionError(
            f"field {sd_definition_name!r} must be sample, population, or unknown"
        )

    return GroupSummary(
        label=label,
        n=n,
        mean=mean,
        sd=sd,
        sd_definition=sd_definition,
        weighted=_bool_field(node, weighted_name),
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
    return _reported_from_field(field, name)


def _reported_from_field(field: ExtractedField, name: str) -> ReportedNumber:
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


def _int_field(
    node: StatisticalObjectNode,
    name: str,
    *,
    required: bool = False,
    default: int | None = None,
) -> int | None:
    field = _field(node, name, required=required)
    if field is None:
        return default
    return _integer_value(field, name)


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
            f"{node.object_type} reconstruction requires field {name!r}"
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


def _integer_value(field: ExtractedField, name: str) -> int:
    value = field.value
    if isinstance(value, bool) or not isinstance(value, int):
        raise ClaimObjectReconstructionError(f"field {name!r} must contain an integer")
    return value


def _single_index(field_name: str, prefix: str) -> int:
    raw = field_name[len(prefix) :]
    try:
        index = int(raw)
    except ValueError as exc:
        raise ClaimObjectReconstructionError(
            f"field {field_name!r} requires an integer index"
        ) from exc
    if index < 0:
        raise ClaimObjectReconstructionError(f"field {field_name!r} requires a non-negative index")
    return index


def _matrix_indexes(field_name: str) -> tuple[int, int]:
    raw = field_name[len(_CELL_PREFIX) :]
    parts = raw.split(":")
    if len(parts) != 2:
        raise ClaimObjectReconstructionError(
            f"field {field_name!r} must use cell:<row>:<column>"
        )
    try:
        row, column = (int(part) for part in parts)
    except ValueError as exc:
        raise ClaimObjectReconstructionError(
            f"field {field_name!r} requires integer matrix indexes"
        ) from exc
    if row < 0 or column < 0:
        raise ClaimObjectReconstructionError(
            f"field {field_name!r} requires non-negative matrix indexes"
        )
    return row, column
