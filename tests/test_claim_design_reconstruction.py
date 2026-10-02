from __future__ import annotations

import pytest

from veritas.claim_design_reconstruction import reconstruct_design_descriptor
from veritas.claim_reconstruction import ClaimObjectReconstructionError
from veritas.claims import ArtifactRef, ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from veritas.detectors.designs import DIDDesignDetector, WeakIVDesignDetector
from veritas.detectors.rdd import RDDDesignDetector
from veritas.models import DIDDesign, IVDesign, RDDDesign, SourceLocation
from veritas.types import CheckStatus, ComparisonOperator


def _field(
    raw: str,
    value,
    *,
    precision: int | None = None,
    operator: ComparisonOperator | None = None,
) -> ExtractedField:
    return ExtractedField(
        raw=raw,
        value=value,
        source=SourceLocation(artifact_id="paper", page=7, section="Methods"),
        extraction_confidence=0.96,
        displayed_precision=precision,
        comparison_operator=operator,
        identity_confidence=0.95,
    )


def _round_trip(node: StatisticalObjectNode) -> StatisticalObjectNode:
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf", sha256="d" * 64))
    graph.add_object(node)
    restored = StatisticalClaimGraph.from_json(graph.to_json())
    return restored.objects[node.object_id]


def test_generic_design_descriptor_reconstructs_did_and_executes_detector():
    node = _round_trip(
        StatisticalObjectNode(
            object_id="design-did",
            object_type="DesignDescriptor",
            fields={
                "design_family": _field("DiD", "did"),
                "periods": _field("8 periods", 8),
                "staggered_adoption": _field("staggered", True),
                "treatment_type": _field("binary", "binary"),
                "estimator": _field("TWFE", "twfe"),
                "event_study": _field("event study", True),
                "heterogeneity_robust_estimator_reported": _field("no", False),
                "treatment_timing": _field("state adoption year", "state adoption year"),
                "comparison_group": _field("not-yet-treated", "not-yet-treated"),
                "event_time_start": _field("-4", -4),
                "event_time_end": _field("5", 5),
                "fixed_effect:0": _field("state FE", "state"),
                "fixed_effect:1": _field("year FE", "year"),
                "clustering:0": _field("state clustered", "state"),
            },
            source=SourceLocation(artifact_id="paper", page=7, section="Methods"),
        )
    )

    design = reconstruct_design_descriptor(node)

    assert isinstance(design, DIDDesign)
    assert design.event_time_window == (-4, 5)
    assert design.fixed_effects == ("state", "year")
    assert design.clustering == ("state",)
    result = DIDDesignDetector().run(design)[0]
    assert result.status is CheckStatus.REVIEW
    assert result.check_id == "staggered_twfe"


def test_generic_design_descriptor_reconstructs_iv_and_preserves_robust_method_inventory():
    node = _round_trip(
        StatisticalObjectNode(
            object_id="design-iv",
            object_type="DesignDescriptor",
            fields={
                "design_family": _field("IV", "iv"),
                "instrument_count": _field("1 instrument", 1),
                "endogenous_regressor_count": _field("1 endogenous", 1),
                "first_stage_reported": _field("yes", True),
                "reduced_form_reported": _field("yes", True),
                "two_stage_least_squares_reported": _field("yes", True),
                "first_stage_f": _field(
                    "F = 8.4",
                    8.4,
                    precision=1,
                    operator=ComparisonOperator.EQ,
                ),
                "uses_f_gt_10_rule_as_validity_claim": _field("no", False),
                "weak_robust_methods_complete": _field("complete", True),
                "weak_robust_method:0": _field("Anderson-Rubin", "Anderson-Rubin"),
            },
            source=SourceLocation(artifact_id="paper", page=9, table="Table 3"),
        )
    )

    design = reconstruct_design_descriptor(node)

    assert isinstance(design, IVDesign)
    assert design.first_stage_f is not None and design.first_stage_f.value == 8.4
    assert design.weak_robust_methods == ("Anderson-Rubin",)
    result = WeakIVDesignDetector().run(design)[0]
    assert result.status is CheckStatus.PASS


def test_generic_design_descriptor_reconstructs_rdd_and_executes_detector():
    node = _round_trip(
        StatisticalObjectNode(
            object_id="design-rdd",
            object_type="DesignDescriptor",
            fields={
                "design_family": _field("RDD", "rdd"),
                "framework": _field("continuity", "continuity"),
                "design_type": _field("sharp", "sharp"),
                "running_variable": _field("score", "score"),
                "cutoff": _field("50", 50.0, precision=0, operator=ComparisonOperator.EQ),
                "bandwidth": _field("8.5", 8.5, precision=1, operator=ComparisonOperator.EQ),
                "bandwidth_selection": _field("MSE optimal", "mse-optimal"),
                "kernel": _field("triangular", "triangular"),
                "robust_bias_corrected_inference": _field("yes", True),
                "alternative_modern_inference_reported": _field("no", False),
            },
            source=SourceLocation(artifact_id="paper", page=11, section="RDD specification"),
        )
    )

    design = reconstruct_design_descriptor(node)

    assert isinstance(design, RDDDesign)
    assert design.cutoff is not None and design.cutoff.value == 50.0
    assert design.bandwidth is not None and design.bandwidth.decimals == 1
    result = RDDDesignDetector().run(design)[0]
    assert result.status is CheckStatus.PASS


def test_did_missing_treatment_type_becomes_unknown_instead_of_binary_default():
    node = StatisticalObjectNode(
        object_id="did-unknown-treatment",
        object_type="DesignDescriptor",
        fields={
            "design_family": _field("did", "did"),
            "periods": _field("2", 2),
            "staggered_adoption": _field("no", False),
        },
        source=SourceLocation(artifact_id="paper", page=2),
    )

    design = reconstruct_design_descriptor(node)

    assert isinstance(design, DIDDesign)
    assert design.treatment_type == "unknown"
    result = DIDDesignDetector().run(design)[0]
    assert result.status is not CheckStatus.PASS


def test_iv_reconstruction_fails_closed_without_complete_robust_method_inventory():
    node = StatisticalObjectNode(
        object_id="iv-incomplete",
        object_type="DesignDescriptor",
        fields={
            "design_family": _field("iv", "iv"),
            "instrument_count": _field("1", 1),
            "endogenous_regressor_count": _field("1", 1),
            "uses_f_gt_10_rule_as_validity_claim": _field("no", False),
        },
        source=SourceLocation(artifact_id="paper", page=3),
    )

    with pytest.raises(ClaimObjectReconstructionError, match="weak_robust_methods_complete"):
        reconstruct_design_descriptor(node)


def test_rdd_numeric_fields_require_explicit_display_operator():
    node = StatisticalObjectNode(
        object_id="rdd-no-operator",
        object_type="DesignDescriptor",
        fields={
            "design_family": _field("rdd", "rdd"),
            "framework": _field("continuity", "continuity"),
            "design_type": _field("sharp", "sharp"),
            "cutoff": _field("0", 0.0, precision=0),
        },
        source=SourceLocation(artifact_id="paper", page=3),
    )

    with pytest.raises(ClaimObjectReconstructionError, match="comparison_operator"):
        reconstruct_design_descriptor(node)


def test_unknown_design_family_is_not_guessed():
    node = StatisticalObjectNode(
        object_id="unknown-design",
        object_type="DesignDescriptor",
        fields={"design_family": _field("synthetic control", "synthetic_control")},
        source=SourceLocation(artifact_id="paper", page=3),
    )

    with pytest.raises(ClaimObjectReconstructionError, match="unsupported design family"):
        reconstruct_design_descriptor(node)
