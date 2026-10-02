from __future__ import annotations

from veritas.claims import ArtifactRef, ExtractedField, StatisticalClaimGraph, StatisticalObjectNode
from veritas.detector_input_reconstruction import reconstruct_detector_input
from veritas.models import DIDDesign, SourceLocation


def _field(raw: str, value) -> ExtractedField:
    return ExtractedField(
        raw=raw,
        value=value,
        source=SourceLocation(artifact_id="paper", page=5),
        extraction_confidence=0.97,
        identity_confidence=0.96,
    )


def test_unified_reconstruction_dispatches_design_descriptor_after_json_round_trip():
    graph = StatisticalClaimGraph()
    graph.add_artifact(ArtifactRef("paper", "pdf", sha256="e" * 64))
    graph.add_object(
        StatisticalObjectNode(
            object_id="design-1",
            object_type="DesignDescriptor",
            fields={
                "design_family": _field("DiD", "did"),
                "periods": _field("2", 2),
                "staggered_adoption": _field("no", False),
                "treatment_type": _field("binary", "binary"),
            },
            source=SourceLocation(artifact_id="paper", page=5),
        )
    )
    restored = StatisticalClaimGraph.from_json(graph.to_json())

    result = reconstruct_detector_input(restored, "design-1")

    assert isinstance(result, DIDDesign)
    assert result.periods == 2
    assert result.staggered_adoption is False
    assert result.treatment_type == "binary"
