from __future__ import annotations

from veritas.data_provenance_integrity import (
    ObservedAssignment,
    ProvenanceCheckStatus,
    RandomizationRecord,
    build_e5_data_provenance_check,
    compare_artifact_identity,
    compare_lineage_origin,
    compare_randomization_record,
)
from veritas.models import SourceLocation
from veritas.sample_lineage import (
    LineageOperation,
    LineageOperationKind,
    SampleLineage,
    SampleSnapshot,
)
from veritas.types import CheckStatus, EvidenceGrade


def test_verified_randomization_assignment_mismatch_is_direct_provenance_concern() -> None:
    record = RandomizationRecord(
        "randomization-v1",
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "blocked random assignment",
        SourceLocation(artifact_id="randomization-record"),
        True,
    )
    observed = ObservedAssignment(
        "b" * 64,
        "d" * 64,
        SourceLocation(artifact_id="analysis-data"),
    )

    concern = compare_randomization_record(record, observed)

    assert concern.status is ProvenanceCheckStatus.MISMATCH
    assert concern.direct_evidence_verified is True
    assert "treatment assignment identity differs" in concern.explanation


def test_unverified_randomization_record_cannot_be_direct_contradiction() -> None:
    record = RandomizationRecord(
        "randomization-v1",
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "simple random assignment",
        SourceLocation(artifact_id="randomization-record"),
        False,
    )
    observed = ObservedAssignment(
        "b" * 64,
        "d" * 64,
        SourceLocation(artifact_id="analysis-data"),
    )

    concern = compare_randomization_record(record, observed)

    assert concern.status is ProvenanceCheckStatus.UNVERIFIABLE
    assert concern.direct_evidence_verified is False


def test_direct_artifact_identity_mismatch_builds_e5_with_mandatory_review() -> None:
    concern = compare_artifact_identity(
        expected_sha256="a" * 64,
        observed_sha256="b" * 64,
        source=SourceLocation(artifact_id="raw-data"),
        identity_basis_verified=True,
    )

    check = build_e5_data_provenance_check(
        (concern,),
        object_id="dataset-main",
        source=SourceLocation(artifact_id="raw-data"),
    )

    assert check.status is CheckStatus.FAIL
    assert check.finding is not None
    assert check.finding.grade is EvidenceGrade.DATA_PROVENANCE_CONCERN
    assert check.finding.evidence["human_review_required"] is True
    assert check.finding.evidence["human_review_status"] == "pending"
    assert check.finding.evidence["intent_inference_authorized"] is False
    assert check.finding.evidence["production_authorized"] is False
    assert "misconduct" in check.finding.explanation
    assert "does not infer" in check.finding.explanation


def test_matching_direct_provenance_returns_pass_without_finding() -> None:
    concern = compare_artifact_identity(
        expected_sha256="a" * 64,
        observed_sha256="a" * 64,
        source=SourceLocation(artifact_id="raw-data"),
        identity_basis_verified=True,
    )

    check = build_e5_data_provenance_check(
        (concern,),
        object_id="dataset-main",
        source=SourceLocation(artifact_id="raw-data"),
    )

    assert check.status is CheckStatus.PASS
    assert check.finding is None


def _verified_snapshot(snapshot_id: str, artifact_char: str, row_char: str) -> SampleSnapshot:
    return SampleSnapshot(
        snapshot_id,
        artifact_char * 64,
        row_char * 64,
        10,
        SourceLocation(artifact_id=snapshot_id),
        True,
    )


def _lineage_with_wrong_origin(*, complete: bool, verify_raw: bool = True) -> SampleLineage:
    lineage = SampleLineage(completeness_verified=complete)
    raw = SampleSnapshot(
        "raw",
        "a" * 64,
        "b" * 64,
        10,
        SourceLocation(artifact_id="raw"),
        verify_raw,
    )
    other = _verified_snapshot("other", "c", "d")
    analysis = _verified_snapshot("analysis", "e", "f")
    for snapshot in (raw, other, analysis):
        lineage.add_snapshot(snapshot)
    lineage.add_operation(
        LineageOperation(
            "other-to-analysis",
            LineageOperationKind.DERIVATION,
            ("other",),
            "analysis",
            "derive analysis data",
            "1" * 64,
            SourceLocation(artifact_id="code"),
        )
    )
    return lineage


def test_verified_complete_lineage_origin_mismatch_can_feed_direct_e5_path() -> None:
    lineage = _lineage_with_wrong_origin(complete=True)
    analysis = lineage.snapshots["analysis"]

    concern = compare_lineage_origin(
        lineage,
        expected_raw_snapshot_id="raw",
        analysis_snapshot_id="analysis",
    )
    check = build_e5_data_provenance_check(
        (concern,),
        object_id="dataset-main",
        source=analysis.source,
    )

    assert concern.status is ProvenanceCheckStatus.MISMATCH
    assert concern.direct_evidence_verified is True
    assert check.finding is not None
    assert check.finding.grade is EvidenceGrade.DATA_PROVENANCE_CONCERN


def test_incomplete_lineage_cannot_feed_direct_e5_path() -> None:
    lineage = _lineage_with_wrong_origin(complete=False)

    concern = compare_lineage_origin(
        lineage,
        expected_raw_snapshot_id="raw",
        analysis_snapshot_id="analysis",
    )
    check = build_e5_data_provenance_check(
        (concern,),
        object_id="dataset-main",
        source=lineage.snapshots["analysis"].source,
    )

    assert concern.status is ProvenanceCheckStatus.UNVERIFIABLE
    assert concern.direct_evidence_verified is False
    assert check.status is CheckStatus.UNVERIFIABLE
    assert check.finding is None


def test_unverified_lineage_endpoint_cannot_feed_direct_e5_path() -> None:
    lineage = _lineage_with_wrong_origin(complete=True, verify_raw=False)

    concern = compare_lineage_origin(
        lineage,
        expected_raw_snapshot_id="raw",
        analysis_snapshot_id="analysis",
    )

    assert concern.status is ProvenanceCheckStatus.UNVERIFIABLE
    assert concern.direct_evidence_verified is False
