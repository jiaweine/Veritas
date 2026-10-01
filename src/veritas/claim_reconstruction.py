from __future__ import annotations

import math

from .claims import ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from .group_stats import GroupSummary, TwoGroupComparison
from .models import (
    CorrelationMatrix,
    DiscreteSummary,
    LogitResult,
    MediationResult,
    RegressionResult,
    ReportedNumber,
    SamplePartition,
    StandardizedRegressionReconstruction,
)

_SUPPORTED_INFERENCE_DISTRIBUTIONS = {"normal", "student_t", "unknown"}
_SUPPORTED_SD_DEFINITIONS = {"sample", "population", "unknown"}
_SUPPORTED_TWO_GROUP_TESTS = {"student_equal_var", "welch", "unknown"}
_SUPPORTED_HEDGES_CORRECTIONS = {"exact_gamma", "approx_4df_minus_1", "unknown"}
_GROUP_COUNT_PREFIX = "group_count:"
_LABEL_PREFIX = "label:"
_CELL_PREFIX = "cell:"
_SUPPORT_PREFIX = "support:"
_PREDICTOR_PREFIX = "predictor:"
_STANDARDIZED_BETA_PREFIX = "standardized_beta:"


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
    if node.object_type == "DiscreteSummary":
        return reconstruct_discrete_summary(node)
    if node.object_type == "LogitResult":
        return reconstruct_logit_result(node)
    if node.object_type == "MediationResult":
        return reconstruct_mediation_result(node)
    if node.object_type == "StandardizedRegressionReconstruction":
        return reconstruct_standardized_regression(graph, node)
    raise ClaimObjectReconstructionError(
        f"unsupported statistical object type: {node.object_type!r}"
    )


def reconstruct_regression_result(node: StatisticalObjectNode) -> RegressionResult:
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
    ci_level = _float_field(node, "ci_level", required=has_ci, default=0.95)
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
    return SamplePartition(
        object_id=node.object_id,
        total_n=total_n,
        groups=groups,
        exhaustive=_bool_field(node, "exhaustive"),
        non_overlapping=non_overlapping,
        explanation_present=_bool_field(node, "explanation_present"),
        source=node.source,
    )


def reconstruct_correlation_matrix(node: StatisticalObjectNode) -> CorrelationMatrix:
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
    if node.object_type != "MeanSD":
        raise ClaimObjectReconstructionError(f"expected MeanSD node, got {node.object_type!r}")
    return _group_summary(node, "")


def reconstruct_group_comparison(node: StatisticalObjectNode) -> TwoGroupComparison:
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


def reconstruct_discrete_summary(node: StatisticalObjectNode) -> DiscreteSummary:
    if node.object_type != "DiscreteSummary":
        raise ClaimObjectReconstructionError(
            f"expected DiscreteSummary node, got {node.object_type!r}"
        )
    n = _int_field(node, "n", required=True)
    assert n is not None
    if n <= 0:
        raise ClaimObjectReconstructionError("DiscreteSummary n must be positive")
    mean = _reported_number(node, "mean", required=True)
    assert mean is not None
    sd = _reported_number(node, "sd")
    support_by_index: dict[int, float] = {}
    for field_name, field in node.fields.items():
        if field_name.startswith(_SUPPORT_PREFIX):
            index = _single_index(field_name, _SUPPORT_PREFIX)
            support_by_index[index] = _finite_number(field, field_name)
    if len(support_by_index) < 2:
        raise ClaimObjectReconstructionError("DiscreteSummary requires at least two support fields")
    if set(support_by_index) != set(range(len(support_by_index))):
        raise ClaimObjectReconstructionError(
            "support indexes must be contiguous and start at zero"
        )
    support = tuple(support_by_index[index] for index in range(len(support_by_index)))
    if len(set(support)) != len(support):
        raise ClaimObjectReconstructionError("DiscreteSummary support values must be unique")
    sd_definition = _string_field(
        node,
        "sd_definition",
        required=sd is not None,
        default="unknown",
    )
    assert sd_definition is not None
    if sd_definition not in _SUPPORTED_SD_DEFINITIONS:
        raise ClaimObjectReconstructionError(
            "sd_definition must be one of sample, population, or unknown"
        )
    support_verified = _bool_field(node, "support_verified", required=True)
    n_verified = _bool_field(node, "n_verified", required=True)
    weighted = _bool_field(node, "weighted", required=True)
    assert support_verified is not None and n_verified is not None and weighted is not None
    return DiscreteSummary(
        object_id=node.object_id,
        n=n,
        mean=mean,
        support=support,
        sd=sd,
        sd_definition=sd_definition,
        support_verified=support_verified,
        n_verified=n_verified,
        weighted=weighted,
        source=node.source,
    )


def reconstruct_logit_result(node: StatisticalObjectNode) -> LogitResult:
    if node.object_type != "LogitResult":
        raise ClaimObjectReconstructionError(
            f"expected LogitResult node, got {node.object_type!r}"
        )
    beta = _reported_number(node, "beta", required=True)
    odds_ratio = _reported_number(node, "odds_ratio", required=True)
    relation_verified = _bool_field(node, "exp_beta_relation_verified", required=True)
    assert beta is not None and odds_ratio is not None and relation_verified is not None
    return LogitResult(
        object_id=node.object_id,
        beta=beta,
        odds_ratio=odds_ratio,
        exp_beta_relation_verified=relation_verified,
        source=node.source,
    )


def reconstruct_mediation_result(node: StatisticalObjectNode) -> MediationResult:
    if node.object_type != "MediationResult":
        raise ClaimObjectReconstructionError(
            f"expected MediationResult node, got {node.object_type!r}"
        )
    a_path = _reported_number(node, "a_path", required=True)
    b_path = _reported_number(node, "b_path", required=True)
    indirect_effect = _reported_number(node, "indirect_effect", required=True)
    product_definition_verified = _bool_field(
        node,
        "product_definition_verified",
        required=True,
    )
    scale_consistent_verified = _bool_field(
        node,
        "scale_consistent_verified",
        required=True,
    )
    assert (
        a_path is not None
        and b_path is not None
        and indirect_effect is not None
        and product_definition_verified is not None
        and scale_consistent_verified is not None
    )
    return MediationResult(
        object_id=node.object_id,
        a_path=a_path,
        b_path=b_path,
        indirect_effect=indirect_effect,
        product_definition_verified=product_definition_verified,
        scale_consistent_verified=scale_consistent_verified,
        source=node.source,
    )


def reconstruct_standardized_regression(
    graph: StatisticalClaimGraph,
    node: StatisticalObjectNode,
) -> StandardizedRegressionReconstruction:
    if node.object_type != "StandardizedRegressionReconstruction":
        raise ClaimObjectReconstructionError(
            "expected StandardizedRegressionReconstruction node, "
            f"got {node.object_type!r}"
        )
    matrix_object_id = _string_field(
        node,
        "correlation_matrix_object_id",
        required=True,
    )
    assert matrix_object_id is not None
    try:
        matrix_node = graph.objects[matrix_object_id]
    except KeyError as exc:
        raise ClaimObjectReconstructionError(
            f"standardized regression references unknown correlation matrix {matrix_object_id!r}"
        ) from exc
    correlation_matrix = reconstruct_correlation_matrix(matrix_node)
    outcome = _string_field(node, "outcome", required=True)
    assert outcome is not None
    predictors_by_index: dict[int, str] = {}
    betas_by_index: dict[int, ReportedNumber] = {}
    for field_name, field in node.fields.items():
        if field_name.startswith(_PREDICTOR_PREFIX):
            index = _single_index(field_name, _PREDICTOR_PREFIX)
            if not isinstance(field.value, str) or not field.value.strip():
                raise ClaimObjectReconstructionError(
                    f"field {field_name!r} must contain a non-empty predictor label"
                )
            predictors_by_index[index] = field.value.strip()
        elif field_name.startswith(_STANDARDIZED_BETA_PREFIX):
            index = _single_index(field_name, _STANDARDIZED_BETA_PREFIX)
            betas_by_index[index] = _reported_from_field(field, field_name)
    if not predictors_by_index:
        raise ClaimObjectReconstructionError(
            "StandardizedRegressionReconstruction requires at least one predictor"
        )
    expected_indexes = set(range(len(predictors_by_index)))
    if set(predictors_by_index) != expected_indexes:
        raise ClaimObjectReconstructionError(
            "predictor indexes must be contiguous and start at zero"
        )
    if set(betas_by_index) != expected_indexes:
        raise ClaimObjectReconstructionError(
            "standardized beta indexes must exactly match predictor indexes"
        )
    predictors = tuple(predictors_by_index[index] for index in range(len(predictors_by_index)))
    if len(set(predictors)) != len(predictors):
        raise ClaimObjectReconstructionError("predictor labels must be unique")
    if outcome in predictors:
        raise ClaimObjectReconstructionError("outcome may not also be a predictor")
    standardized_betas = tuple(betas_by_index[index] for index in range(len(betas_by_index)))
    ols_identity_verified = _bool_field(node, "ols_identity_verified", required=True)
    same_sample_verified = _bool_field(node, "same_sample_verified", required=True)
    complete_predictor_set_verified = _bool_field(
        node,
        "complete_predictor_set_verified",
        required=True,
    )
    assert (
        ols_identity_verified is not None
        and same_sample_verified is not None
        and complete_predictor_set_verified is not None
    )
    return StandardizedRegressionReconstruction(
        object_id=node.object_id,
        correlation_matrix=correlation_matrix,
        outcome=outcome,
        predictors=predictors,
        standardized_betas=standardized_betas,
        ols_identity_verified=ols_identity_verified,
        same_sample_verified=same_sample_verified,
        complete_predictor_set_verified=complete_predictor_set_verified,
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
