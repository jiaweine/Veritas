from __future__ import annotations

import pytest

from veritas.models import SourceLocation
from veritas.sample_lineage import (
    LineageOperation,
    LineageOperationKind,
    SampleLineage,
    SampleSnapshot,
    find_undocumented_lineage_operations,
    row_identity_sha256,
)


def _snapshot(snapshot_id: str, n: int, char: str) -> SampleSnapshot:
    return SampleSnapshot(
        snapshot_id,
        char * 64,
        row_identity_sha256(tuple(f"id-{i}" for i in range(n))),
        n,
        SourceLocation(artifact_id=snapshot_id),
    )


def test_raw_to_analysis_lineage_tracks_exclusion_and_transformation() -> None:
    lineage = SampleLineage()
    for snapshot in (
        _snapshot("raw", 5, "a"),
        _snapshot("filtered", 4, "b"),
        _snapshot("analysis", 4, "c"),
    ):
        lineage.add_snapshot(snapshot)
    lineage.add_operation(
        LineageOperation(
            "drop-missing",
            LineageOperationKind.EXCLUSION,
            ("raw",),
            "filtered",
            "drop one record with missing primary outcome",
            "d" * 64,
            SourceLocation(artifact_id="code", section="filter"),
            "exclude-missing",
        )
    )
    lineage.add_operation(
        LineageOperation(
            "log-income",
            LineageOperationKind.TRANSFORMATION,
            ("filtered",),
            "analysis",
            "construct log income",
            "e" * 64,
            SourceLocation(artifact_id="code", section="transform"),
        )
    )

    assert set(lineage.trace_ancestors("analysis")) == {"raw", "filtered"}
    concerns = find_undocumented_lineage_operations(
        lineage,
        registered_plan_item_ids=("exclude-missing",),
    )
    assert [item.operation_id for item in concerns] == ["log-income"]
    assert concerns[0].kind is LineageOperationKind.TRANSFORMATION
    assert len(lineage.sha256()) == 64


def test_filter_cannot_increase_row_count_without_mutating_state() -> None:
    lineage = SampleLineage()
    lineage.add_snapshot(_snapshot("raw", 4, "a"))
    lineage.add_snapshot(_snapshot("filtered", 5, "b"))

    with pytest.raises(ValueError, match="cannot increase"):
        lineage.add_operation(
            LineageOperation(
                "bad-filter",
                LineageOperationKind.FILTER,
                ("raw",),
                "filtered",
                "impossible filter",
                "c" * 64,
                SourceLocation(artifact_id="code"),
            )
        )

    assert lineage.operations == {}
    lineage.validate()


def test_transformation_must_preserve_row_count_without_mutating_state() -> None:
    lineage = SampleLineage()
    lineage.add_snapshot(_snapshot("before", 4, "a"))
    lineage.add_snapshot(_snapshot("after", 3, "b"))

    with pytest.raises(ValueError, match="preserve sample row count"):
        lineage.add_operation(
            LineageOperation(
                "bad-transform",
                LineageOperationKind.TRANSFORMATION,
                ("before",),
                "after",
                "transform variable",
                "c" * 64,
                SourceLocation(artifact_id="code"),
            )
        )

    assert lineage.operations == {}


def test_lineage_cycle_fails_closed_without_mutating_state() -> None:
    lineage = SampleLineage()
    lineage.add_snapshot(_snapshot("a", 4, "a"))
    lineage.add_snapshot(_snapshot("b", 4, "b"))
    lineage.add_operation(
        LineageOperation(
            "a-to-b",
            LineageOperationKind.TRANSFORMATION,
            ("a",),
            "b",
            "first transform",
            "c" * 64,
            SourceLocation(artifact_id="code"),
        )
    )

    with pytest.raises(ValueError, match="acyclic"):
        lineage.add_operation(
            LineageOperation(
                "b-to-a",
                LineageOperationKind.TRANSFORMATION,
                ("b",),
                "a",
                "cyclic transform",
                "d" * 64,
                SourceLocation(artifact_id="code"),
            )
        )

    assert set(lineage.operations) == {"a-to-b"}
    lineage.validate()


def test_row_identity_hash_is_order_invariant_but_rejects_duplicates() -> None:
    assert row_identity_sha256(("b", "a")) == row_identity_sha256(("a", "b"))
    with pytest.raises(ValueError, match="unique"):
        row_identity_sha256(("a", "a"))
