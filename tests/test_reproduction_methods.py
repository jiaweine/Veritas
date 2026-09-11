from __future__ import annotations

import pytest

from veritas.reproduction import MethodField, MethodSpecification
from veritas.reproduction_methods import (
    build_method_specification,
    get_reproduction_method_contract,
    validate_method_specification_contract,
)


def test_did_contract_materializes_missing_required_choices_as_unverifiable() -> None:
    spec = build_method_specification(
        spec_id="did-main",
        contract_id="did_v1",
        fields=(
            MethodField("outcome", "employment"),
            MethodField("treatment_definition", "policy adoption"),
            MethodField("treatment_timing", "first adoption year"),
            MethodField("sample_rule", "states 2000-2020"),
            MethodField("estimator", "group-time ATT"),
            MethodField("inference", "clustered by state"),
        ),
    )

    assert "comparison_group" in spec.missing_required_fields()
    assert spec.field_map()["comparison_group"].confidence == 0.0
    assert spec.object_type == "DIDEstimate"


def test_rdd_contract_requires_bandwidth_kernel_and_polynomial_identity() -> None:
    contract = get_reproduction_method_contract("rdd_v1")
    assert {"cutoff", "bandwidth_rule", "polynomial_order", "kernel"}.issubset(
        contract.required_fields
    )


def test_contract_rejects_undeclared_method_fields() -> None:
    with pytest.raises(ValueError, match="not declared"):
        build_method_specification(
            spec_id="ols-main",
            contract_id="regression_v1",
            fields=(
                MethodField("outcome", "y"),
                MethodField("focal_predictor", "x"),
                MethodField("estimator", "ols"),
                MethodField("sample_rule", "all rows"),
                MethodField("model_formula", "y ~ x"),
                MethodField("inference", "HC2"),
                MethodField("secret_choice", "not in contract"),
            ),
        )


def test_contract_validation_rejects_hand_built_spec_that_omits_required_field() -> None:
    spec = MethodSpecification(
        spec_id="manual",
        object_type="RegressionResult",
        version="regression_v1:1",
        fields=(
            MethodField("outcome", "y"),
            MethodField("focal_predictor", "x"),
            MethodField("sample_rule", "all rows"),
            MethodField("estimator", "ols"),
            MethodField("model_formula", "y ~ x"),
        ),
    )

    assert spec.missing_required_fields() == ()
    with pytest.raises(ValueError, match="omitted required contract fields"):
        validate_method_specification_contract(spec)


def test_contract_validation_requires_explicit_contract_version_binding() -> None:
    spec = MethodSpecification(
        spec_id="manual",
        object_type="RegressionResult",
        fields=(
            MethodField("outcome", "y"),
            MethodField("focal_predictor", "x"),
            MethodField("sample_rule", "all rows"),
            MethodField("estimator", "ols"),
            MethodField("model_formula", "y ~ x"),
            MethodField("inference", "HC2"),
        ),
    )

    with pytest.raises(ValueError, match="contract_id:version"):
        validate_method_specification_contract(spec)
