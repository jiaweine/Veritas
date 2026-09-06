from __future__ import annotations

import pytest

from veritas.reproduction_provenance import (
    ProvenanceArtifact,
    ProvenanceArtifactRole,
    ProvenanceTransform,
    ReproductionProvenanceGraph,
)


def _artifact(artifact_id: str, role: ProvenanceArtifactRole, char: str) -> ProvenanceArtifact:
    return ProvenanceArtifact(artifact_id, role, char * 64)


def test_processed_data_and_generated_output_have_data_and_code_ancestry() -> None:
    graph = ReproductionProvenanceGraph()
    for artifact in (
        _artifact("raw", ProvenanceArtifactRole.RAW_DATA, "a"),
        _artifact("clean-code", ProvenanceArtifactRole.CODE, "b"),
        _artifact("analysis", ProvenanceArtifactRole.ANALYSIS_DATA, "c"),
        _artifact("model-code", ProvenanceArtifactRole.CODE, "d"),
        _artifact("table", ProvenanceArtifactRole.GENERATED_TABLE, "e"),
    ):
        graph.add_artifact(artifact)
    graph.add_transform(
        ProvenanceTransform(
            "clean",
            "clean-code",
            ("raw",),
            ("analysis",),
            "f" * 64,
        )
    )
    graph.add_transform(
        ProvenanceTransform(
            "estimate",
            "model-code",
            ("analysis",),
            ("table",),
            "1" * 64,
        )
    )

    graph.validate_reproducible_output("table")
    ancestors = set(graph.ancestors("table"))
    assert {"raw", "clean-code", "analysis", "model-code"} <= ancestors
    assert len(graph.sha256()) == 64


def test_provenance_graph_rejects_multiple_producers_without_mutating_state() -> None:
    graph = ReproductionProvenanceGraph()
    for artifact in (
        _artifact("raw", ProvenanceArtifactRole.RAW_DATA, "a"),
        _artifact("code-1", ProvenanceArtifactRole.CODE, "b"),
        _artifact("code-2", ProvenanceArtifactRole.CODE, "c"),
        _artifact("out", ProvenanceArtifactRole.ANALYSIS_DATA, "d"),
    ):
        graph.add_artifact(artifact)
    graph.add_transform(
        ProvenanceTransform("first", "code-1", ("raw",), ("out",), "e" * 64)
    )

    with pytest.raises(ValueError, match="multiple producing transforms"):
        graph.add_transform(
            ProvenanceTransform("second", "code-2", ("raw",), ("out",), "f" * 64)
        )

    assert set(graph.transforms) == {"first"}
    graph.validate()


def test_provenance_graph_rejects_cycles_without_mutating_state() -> None:
    graph = ReproductionProvenanceGraph()
    for artifact in (
        _artifact("a", ProvenanceArtifactRole.ANALYSIS_DATA, "a"),
        _artifact("b", ProvenanceArtifactRole.ANALYSIS_DATA, "b"),
        _artifact("code-1", ProvenanceArtifactRole.CODE, "c"),
        _artifact("code-2", ProvenanceArtifactRole.CODE, "d"),
    ):
        graph.add_artifact(artifact)
    graph.add_transform(
        ProvenanceTransform("a-to-b", "code-1", ("a",), ("b",), "e" * 64)
    )

    with pytest.raises(ValueError, match="acyclic"):
        graph.add_transform(
            ProvenanceTransform("b-to-a", "code-2", ("b",), ("a",), "f" * 64)
        )

    assert set(graph.transforms) == {"a-to-b"}
    graph.validate()


def test_output_without_data_ancestor_fails_closed() -> None:
    graph = ReproductionProvenanceGraph()
    graph.add_artifact(_artifact("code", ProvenanceArtifactRole.CODE, "a"))
    graph.add_artifact(_artifact("out", ProvenanceArtifactRole.GENERATED_FIGURE, "b"))
    graph.add_transform(
        ProvenanceTransform("render", "code", ("code",), ("out",), "c" * 64)
    )

    with pytest.raises(ValueError, match="no data ancestor"):
        graph.validate_reproducible_output("out")
