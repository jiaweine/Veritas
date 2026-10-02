from __future__ import annotations

import math

from .claim_reconstruction import ClaimObjectReconstructionError
from .claims import ExtractedField, StatisticalObjectNode
from .models import DIDDesign, IVDesign, RDDDesign, ReportedNumber

_DESIGN_TYPES = {"DesignDescriptor", "DIDDesign", "IVDesign", "RDDDesign"}
_DID_FAMILIES = {"did", "difference_in_differences", "difference-in-differences"}
_IV_FAMILIES = {"iv", "instrumental_variables", "instrumental-variables", "2sls"}
_RDD_FAMILIES = {"rdd", "regression_discontinuity", "regression-discontinuity"}


def reconstruct_design_descriptor(node: StatisticalObjectNode) -> DIDDesign | IVDesign | RDDDesign:
    """Reconstruct a typed design object without parser state or permissive guessing.

    `DesignDescriptor` nodes carry an explicit `design_family` field. Dedicated
    `DIDDesign`, `IVDesign`, and `RDDDesign` node types are also accepted, but an
    explicit family is still required when the generic node type is used.

    Fields that would otherwise make detector applicability optimistic are
    required or converted to conservative unknown values. In particular, a
    missing DiD treatment type never inherits the model's binary default, and an
    IV object cannot treat an omitted weak-robust-method inventory as evidence
    that no robust method was reported.
    """

    if node.object_type not in _DESIGN_TYPES:
        raise ClaimObjectReconstructionError(
            f"expected design descriptor node, got {node.object_type!r}"
        )
    family = _design_family(node)
    if family == "did":
        return reconstruct_did_design(node)
    if family == "iv":
        return reconstruct_iv_design(node)
    if family == "rdd":
        return reconstruct_rdd_design(node)
    raise ClaimObjectReconstructionError(f"unsupported design family: {family!r}")


def reconstruct_did_design(node: StatisticalObjectNode) -> DIDDesign:
    _expect_family(node, "did")
    periods = _int_field(node, "periods")
    if periods is not None and periods < 2:
        raise ClaimObjectReconstructionError("DID periods must be at least 2")
    treatment_type = _string_field(node, "treatment_type", default="unknown")
    assert treatment_type is not None
    if treatment_type not in {"binary", "continuous", "unknown"}:
        raise ClaimObjectReconstructionError(
            "DID treatment_type must be binary, continuous, or unknown"
        )
    event_start = _int_field(node, "event_time_start")
    event_end = _int_field(node, "event_time_end")
    if (event_start is None) != (event_end is None):
        raise ClaimObjectReconstructionError(
            "DID event-time window requires both event_time_start and event_time_end"
        )
    if event_start is not None and event_end is not None and event_start > event_end:
        raise ClaimObjectReconstructionError("DID event-time window start exceeds end")
    return DIDDesign(
        object_id=node.object_id,
        periods=periods,
        staggered_adoption=_bool_field(node, "staggered_adoption"),
        treatment_type=treatment_type,
        estimator=_string_field(node, "estimator"),
        event_study=_bool_field(node, "event_study"),
        heterogeneity_robust_estimator_reported=_bool_field(
            node, "heterogeneity_robust_estimator_reported"
        ),
        treatment_timing=_string_field(node, "treatment_timing"),
        comparison_group=_string_field(node, "comparison_group"),
        event_time_window=(event_start, event_end) if event_start is not None else None,
        fixed_effects=_indexed_strings(node, "fixed_effect:"),
        clustering=_indexed_strings(node, "clustering:"),
        pretrend_test=_string_field(node, "pretrend_test"),
        parallel_trends_claimed=_bool_field(node, "parallel_trends_claimed"),
        source=node.source,
    )


def reconstruct_iv_design(node: StatisticalObjectNode) -> IVDesign:
    _expect_family(node, "iv")
    instrument_count = _int_field(node, "instrument_count")
    endogenous_count = _int_field(node, "endogenous_regressor_count")
    if instrument_count is not None and instrument_count < 1:
        raise ClaimObjectReconstructionError("IV instrument_count must be positive")
    if endogenous_count is not None and endogenous_count < 1:
        raise ClaimObjectReconstructionError("IV endogenous_regressor_count must be positive")

    inventory_complete = _bool_field(
        node,
        "weak_robust_methods_complete",
        required=True,
    )
    if inventory_complete is not True:
        raise ClaimObjectReconstructionError(
            "IV weak_robust_methods_complete must be explicitly true before detector input reconstruction"
        )
    f_rule_claim = _bool_field(
        node,
        "uses_f_gt_10_rule_as_validity_claim",
        required=True,
    )
    assert f_rule_claim is not None
    return IVDesign(
        object_id=node.object_id,
        single_instrument=_bool_field(node, "single_instrument"),
        single_endogenous_regressor=_bool_field(node, "single_endogenous_regressor"),
        just_identified=_bool_field(node, "just_identified"),
        instrument_count=instrument_count,
        endogenous_regressor_count=endogenous_count,
        first_stage_reported=_bool_field(node, "first_stage_reported"),
        reduced_form_reported=_bool_field(node, "reduced_form_reported"),
        two_stage_least_squares_reported=_bool_field(
            node, "two_stage_least_squares_reported"
        ),
        first_stage_f=_reported_number(node, "first_stage_f"),
        uses_f_gt_10_rule_as_validity_claim=f_rule_claim,
        weak_robust_methods=_indexed_strings(node, "weak_robust_method:"),
        source=node.source,
    )


def reconstruct_rdd_design(node: StatisticalObjectNode) -> RDDDesign:
    _expect_family(node, "rdd")
    framework = _string_field(node, "framework", required=True)
    design_type = _string_field(node, "design_type", required=True)
    assert framework is not None and design_type is not None
    if framework not in {"continuity", "local_randomization", "unknown"}:
        raise ClaimObjectReconstructionError(
            "RDD framework must be continuity, local_randomization, or unknown"
        )
    if design_type not in {"sharp", "fuzzy", "unknown"}:
        raise ClaimObjectReconstructionError("RDD design_type must be sharp, fuzzy, or unknown")
    polynomial_order = _int_field(node, "global_polynomial_order")
    if polynomial_order is not None and polynomial_order < 0:
        raise ClaimObjectReconstructionError("RDD global_polynomial_order must be non-negative")
    return RDDDesign(
        object_id=node.object_id,
        framework=framework,
        design_type=design_type,
        estimator=_string_field(node, "estimator"),
        running_variable=_string_field(node, "running_variable"),
        cutoff=_reported_number(node, "cutoff"),
        bandwidth=_reported_number(node, "bandwidth"),
        bandwidth_selection=_string_field(node, "bandwidth_selection"),
        kernel=_string_field(node, "kernel"),
        inference_description=_string_field(node, "inference_description"),
        global_polynomial_order=polynomial_order,
        robust_bias_corrected_inference=_bool_field(
            node, "robust_bias_corrected_inference"
        ),
        alternative_modern_inference_reported=_bool_field(
            node, "alternative_modern_inference_reported"
        ),
        randomization_inference_reported=_bool_field(
            node, "randomization_inference_reported"
        ),
        continuity_check_claimed=_bool_field(node, "continuity_check_claimed"),
        continuity_check_reported=_bool_field(node, "continuity_check_reported"),
        manipulation_check_claimed=_bool_field(node, "manipulation_check_claimed"),
        density_test_reported=_bool_field(node, "density_test_reported"),
        source=node.source,
    )


def _design_family(node: StatisticalObjectNode) -> str:
    if node.object_type == "DIDDesign":
        return "did"
    if node.object_type == "IVDesign":
        return "iv"
    if node.object_type == "RDDDesign":
        return "rdd"
    raw = _string_field(node, "design_family", required=True)
    assert raw is not None
    normalized = raw.strip().lower()
    if normalized in _DID_FAMILIES:
        return "did"
    if normalized in _IV_FAMILIES:
        return "iv"
    if normalized in _RDD_FAMILIES:
        return "rdd"
    return normalized


def _expect_family(node: StatisticalObjectNode, expected: str) -> None:
    actual = _design_family(node)
    if actual != expected:
        raise ClaimObjectReconstructionError(
            f"expected {expected!r} design family, got {actual!r}"
        )


def _field(
    node: StatisticalObjectNode,
    name: str,
    *,
    required: bool = False,
) -> ExtractedField | None:
    field = node.fields.get(name)
    if field is None and required:
        raise ClaimObjectReconstructionError(
            f"{node.object_type} reconstruction requires field {name!r}"
        )
    return field


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
) -> bool | None:
    field = _field(node, name, required=required)
    if field is None:
        return None
    if not isinstance(field.value, bool):
        raise ClaimObjectReconstructionError(f"field {name!r} must contain a boolean")
    return field.value


def _int_field(node: StatisticalObjectNode, name: str) -> int | None:
    field = _field(node, name)
    if field is None:
        return None
    if isinstance(field.value, bool) or not isinstance(field.value, int):
        raise ClaimObjectReconstructionError(f"field {name!r} must contain an integer")
    return field.value


def _reported_number(node: StatisticalObjectNode, name: str) -> ReportedNumber | None:
    field = _field(node, name)
    if field is None:
        return None
    if isinstance(field.value, bool) or not isinstance(field.value, (int, float)):
        raise ClaimObjectReconstructionError(f"field {name!r} must contain a numeric value")
    value = float(field.value)
    if not math.isfinite(value):
        raise ClaimObjectReconstructionError(f"field {name!r} must contain a finite value")
    if field.comparison_operator is None:
        raise ClaimObjectReconstructionError(
            f"field {name!r} is missing an explicit comparison_operator"
        )
    return ReportedNumber(
        value=value,
        decimals=field.displayed_precision,
        operator=field.comparison_operator,
    )


def _indexed_strings(node: StatisticalObjectNode, prefix: str) -> tuple[str, ...]:
    values: dict[int, str] = {}
    for field_name, field in node.fields.items():
        if not field_name.startswith(prefix):
            continue
        raw_index = field_name[len(prefix) :]
        try:
            index = int(raw_index)
        except ValueError as exc:
            raise ClaimObjectReconstructionError(
                f"field {field_name!r} requires an integer index"
            ) from exc
        if index < 0:
            raise ClaimObjectReconstructionError(
                f"field {field_name!r} requires a non-negative index"
            )
        if not isinstance(field.value, str) or not field.value.strip():
            raise ClaimObjectReconstructionError(
                f"field {field_name!r} must contain a non-empty string"
            )
        values[index] = field.value.strip()
    if set(values) != set(range(len(values))):
        raise ClaimObjectReconstructionError(
            f"{prefix[:-1]} indexes must be contiguous and start at zero"
        )
    return tuple(values[index] for index in range(len(values)))
