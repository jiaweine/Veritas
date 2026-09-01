from __future__ import annotations

from dataclasses import dataclass

from .reproduction import MethodField, MethodSpecification


@dataclass(frozen=True)
class ReproductionMethodContract:
    contract_id: str
    object_type: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    rationale: str = ""
    version: str = "1"

    def __post_init__(self) -> None:
        if not self.contract_id.strip() or not self.object_type.strip():
            raise ValueError("contract_id and object_type are required")
        if len(set(self.required_fields)) != len(self.required_fields):
            raise ValueError("required_fields must be unique")
        if set(self.required_fields) & set(self.optional_fields):
            raise ValueError("a method field cannot be both required and optional")


METHOD_CONTRACTS: tuple[ReproductionMethodContract, ...] = (
    ReproductionMethodContract(
        contract_id="regression_v1",
        object_type="RegressionResult",
        required_fields=(
            "outcome",
            "focal_predictor",
            "sample_rule",
            "estimator",
            "model_formula",
            "inference",
        ),
        optional_fields=(
            "controls",
            "interactions",
            "fixed_effects",
            "weights",
            "offset",
            "transformations",
            "missing_data_rule",
        ),
        rationale="Coefficient and p-value reproduction requires the same estimand, sample, model and inference rule.",
    ),
    ReproductionMethodContract(
        contract_id="did_v1",
        object_type="DIDEstimate",
        required_fields=(
            "outcome",
            "treatment_definition",
            "treatment_timing",
            "comparison_group",
            "sample_rule",
            "estimator",
            "inference",
        ),
        optional_fields=(
            "event_window",
            "reference_period",
            "controls",
            "fixed_effects",
            "weights",
            "anticipation_rule",
            "aggregation_rule",
            "clustering",
        ),
        rationale=(
            "DID implementations with different treatment timing, comparison groups, or estimators may target "
            "different causal parameters even when formulas look similar."
        ),
    ),
    ReproductionMethodContract(
        contract_id="iv_v1",
        object_type="IVEstimate",
        required_fields=(
            "outcome",
            "endogenous_variable",
            "instrument",
            "sample_rule",
            "estimator",
            "inference",
        ),
        optional_fields=(
            "controls",
            "fixed_effects",
            "weights",
            "clustering",
            "weak_iv_procedure",
            "first_stage_formula",
        ),
        rationale="Instrument identity, first/second-stage specification and inference determine the IV estimand and uncertainty.",
    ),
    ReproductionMethodContract(
        contract_id="rdd_v1",
        object_type="RDDResult",
        required_fields=(
            "outcome",
            "running_variable",
            "cutoff",
            "sample_rule",
            "estimand",
            "bandwidth_rule",
            "polynomial_order",
            "kernel",
            "inference",
        ),
        optional_fields=(
            "covariates",
            "bias_correction",
            "clustering",
            "mass_point_handling",
            "donut_rule",
        ),
        rationale="RDD results are not comparable unless cutoff, local sample, bandwidth, polynomial/kernel and inference agree.",
    ),
    ReproductionMethodContract(
        contract_id="survey_regression_v1",
        object_type="SurveyRegressionResult",
        required_fields=(
            "outcome_construction",
            "focal_predictor",
            "sample_rule",
            "estimator",
            "missing_data_rule",
            "inference",
        ),
        optional_fields=(
            "item_scoring",
            "reverse_coding",
            "survey_weights",
            "strata",
            "clusters",
            "controls",
            "transformations",
        ),
        rationale="Survey results can shift materially through scale construction, missing-data handling and design weighting.",
    ),
    ReproductionMethodContract(
        contract_id="sem_v1",
        object_type="SEMResult",
        required_fields=(
            "observed_variables",
            "latent_variable_definition",
            "structural_paths",
            "sample_rule",
            "estimator",
            "missing_data_rule",
            "fit_measure_definition",
        ),
        optional_fields=(
            "constraints",
            "standardization",
            "robust_correction",
            "bootstrap_rule",
        ),
        rationale="SEM reproduction requires the same measurement model, structural model, estimator and missing-data rule.",
    ),
    ReproductionMethodContract(
        contract_id="meta_analysis_v1",
        object_type="MetaAnalysisResult",
        required_fields=(
            "study_set_rule",
            "effect_size_definition",
            "variance_definition",
            "pooling_model",
            "heterogeneity_estimator",
        ),
        optional_fields=(
            "small_sample_correction",
            "prediction_interval_method",
            "dependency_handling",
            "moderators",
        ),
        rationale="Meta-analysis reproduction requires identical study inclusion, effect construction and pooling/heterogeneity methods.",
    ),
)


def get_reproduction_method_contract(contract_id: str) -> ReproductionMethodContract:
    for contract in METHOD_CONTRACTS:
        if contract.contract_id == contract_id:
            return contract
    raise KeyError(contract_id)


def build_method_specification(
    *,
    spec_id: str,
    contract_id: str,
    fields: tuple[MethodField, ...],
) -> MethodSpecification:
    """Apply design-specific requiredness without inventing missing method choices."""
    contract = get_reproduction_method_contract(contract_id)
    known = set(contract.required_fields) | set(contract.optional_fields)
    supplied = {field.name: field for field in fields}
    unknown = tuple(sorted(set(supplied) - known))
    if unknown:
        raise ValueError(f"method fields are not declared by {contract_id}: {unknown!r}")

    materialized: list[MethodField] = []
    for name in contract.required_fields + contract.optional_fields:
        original = supplied.get(name)
        if original is None:
            if name in contract.required_fields:
                materialized.append(MethodField(name=name, value=None, confidence=0.0, required_for_execution=True))
            continue
        materialized.append(
            MethodField(
                name=original.name,
                value=original.value,
                source=original.source,
                confidence=original.confidence,
                required_for_execution=name in contract.required_fields,
            )
        )

    return MethodSpecification(
        spec_id=spec_id,
        object_type=contract.object_type,
        fields=tuple(materialized),
        version=f"{contract.contract_id}:{contract.version}",
    )
