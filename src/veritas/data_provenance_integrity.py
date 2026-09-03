from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum

from .models import CheckResult, Finding, SourceLocation
from .sample_lineage import SampleLineage
from .types import CheckStatus, EvidenceFamily, EvidenceGrade, Materiality

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProvenanceCheckStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNVERIFIABLE = "unverifiable"


class ProvenanceConcernKind(str, Enum):
    ARTIFACT_IDENTITY = "artifact_identity"
    RANDOMIZATION_RECORD = "randomization_record"
    SAMPLE_LINEAGE = "sample_lineage"


@dataclass(frozen=True)
class RandomizationRecord:
    record_id: str
    artifact_sha256: str
    unit_universe_sha256: str
    treatment_assignment_sha256: str
    algorithm: str
    source: SourceLocation
    artifact_identity_verified: bool
    seed_commitment_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not self.record_id.strip():
            raise ValueError("randomization record_id is required")
        for label, value in (
            ("artifact_sha256", self.artifact_sha256),
            ("unit_universe_sha256", self.unit_universe_sha256),
            ("treatment_assignment_sha256", self.treatment_assignment_sha256),
        ):
            _require_sha256(value, label=label)
        if self.seed_commitment_sha256 is not None:
            _require_sha256(self.seed_commitment_sha256, label="seed_commitment_sha256")
        if not isinstance(self.algorithm, str) or not self.algorithm.strip():
            raise ValueError("randomization algorithm is required")
        if type(self.artifact_identity_verified) is not bool:
            raise TypeError("randomization artifact_identity_verified must be a boolean")


@dataclass(frozen=True)
class ObservedAssignment:
    unit_universe_sha256: str
    treatment_assignment_sha256: str
    source: SourceLocation
    extraction_confidence: float = 1.0

    def __post_init__(self) -> None:
        _require_sha256(self.unit_universe_sha256, label="observed unit_universe_sha256")
        _require_sha256(
            self.treatment_assignment_sha256,
            label="observed treatment_assignment_sha256",
        )
        if isinstance(self.extraction_confidence, bool) or not isinstance(
            self.extraction_confidence, (int, float)
        ):
            raise TypeError("observed assignment extraction_confidence must be numeric")
        if not 0.0 <= float(self.extraction_confidence) <= 1.0:
            raise ValueError("observed assignment extraction_confidence must be in [0, 1]")


@dataclass(frozen=True)
class ProvenanceConcern:
    kind: ProvenanceConcernKind
    status: ProvenanceCheckStatus
    explanation: str
    source: SourceLocation
    evidence_sha256: tuple[str, ...]
    direct_evidence_verified: bool

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProvenanceConcernKind):
            raise TypeError("provenance concern kind must be a ProvenanceConcernKind")
        if not isinstance(self.status, ProvenanceCheckStatus):
            raise TypeError("provenance concern status must be a ProvenanceCheckStatus")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValueError("provenance concern explanation is required")
        if not self.evidence_sha256:
            raise ValueError("provenance concern requires at least one evidence hash")
        for value in self.evidence_sha256:
            _require_sha256(value, label="provenance concern evidence_sha256")
        if type(self.direct_evidence_verified) is not bool:
            raise TypeError("direct_evidence_verified must be a boolean")


def compare_randomization_record(
    record: RandomizationRecord,
    observed: ObservedAssignment,
    *,
    minimum_extraction_confidence: float = 0.95,
) -> ProvenanceConcern:
    if not 0.0 <= minimum_extraction_confidence <= 1.0:
        raise ValueError("minimum_extraction_confidence must be in [0, 1]")
    evidence = (
        record.artifact_sha256,
        record.unit_universe_sha256,
        record.treatment_assignment_sha256,
        observed.unit_universe_sha256,
        observed.treatment_assignment_sha256,
    )
    if not record.artifact_identity_verified or observed.extraction_confidence < minimum_extraction_confidence:
        return ProvenanceConcern(
            ProvenanceConcernKind.RANDOMIZATION_RECORD,
            ProvenanceCheckStatus.UNVERIFIABLE,
            "randomization record identity or observed assignment extraction is not verified",
            observed.source,
            evidence,
            False,
        )
    mismatches: list[str] = []
    if record.unit_universe_sha256 != observed.unit_universe_sha256:
        mismatches.append("unit universe identity differs")
    if record.treatment_assignment_sha256 != observed.treatment_assignment_sha256:
        mismatches.append("treatment assignment identity differs")
    if mismatches:
        return ProvenanceConcern(
            ProvenanceConcernKind.RANDOMIZATION_RECORD,
            ProvenanceCheckStatus.MISMATCH,
            "; ".join(mismatches),
            observed.source,
            evidence,
            True,
        )
    return ProvenanceConcern(
        ProvenanceConcernKind.RANDOMIZATION_RECORD,
        ProvenanceCheckStatus.MATCH,
        "observed assignment matches the verified randomization record",
        observed.source,
        evidence,
        True,
    )


def compare_artifact_identity(
    *,
    expected_sha256: str,
    observed_sha256: str,
    source: SourceLocation,
    identity_basis_verified: bool,
) -> ProvenanceConcern:
    _require_sha256(expected_sha256, label="expected artifact sha256")
    _require_sha256(observed_sha256, label="observed artifact sha256")
    if type(identity_basis_verified) is not bool:
        raise TypeError("identity_basis_verified must be a boolean")
    if not identity_basis_verified:
        status = ProvenanceCheckStatus.UNVERIFIABLE
        explanation = "expected artifact identity has not been independently verified"
        direct = False
    elif expected_sha256 != observed_sha256:
        status = ProvenanceCheckStatus.MISMATCH
        explanation = "observed artifact bytes do not match the verified expected artifact identity"
        direct = True
    else:
        status = ProvenanceCheckStatus.MATCH
        explanation = "observed artifact bytes match the verified expected artifact identity"
        direct = True
    return ProvenanceConcern(
        ProvenanceConcernKind.ARTIFACT_IDENTITY,
        status,
        explanation,
        source,
        (expected_sha256, observed_sha256),
        direct,
    )


def compare_lineage_origin(
    lineage: SampleLineage,
    *,
    expected_raw_snapshot_id: str,
    analysis_snapshot_id: str,
) -> ProvenanceConcern:
    lineage.validate()
    if expected_raw_snapshot_id not in lineage.snapshots:
        raise ValueError("expected raw snapshot is not present in the lineage")
    if analysis_snapshot_id not in lineage.snapshots:
        raise ValueError("analysis snapshot is not present in the lineage")
    raw = lineage.snapshots[expected_raw_snapshot_id]
    analysis = lineage.snapshots[analysis_snapshot_id]
    ancestors = set(lineage.trace_ancestors(analysis_snapshot_id))
    if expected_raw_snapshot_id == analysis_snapshot_id or expected_raw_snapshot_id in ancestors:
        status = ProvenanceCheckStatus.MATCH
        explanation = "analysis sample is connected to the verified expected raw snapshot"
    else:
        status = ProvenanceCheckStatus.MISMATCH
        explanation = "analysis sample is not connected to the verified expected raw snapshot"
    return ProvenanceConcern(
        ProvenanceConcernKind.SAMPLE_LINEAGE,
        status,
        explanation,
        analysis.source,
        (raw.artifact_sha256, analysis.artifact_sha256, lineage.sha256()),
        True,
    )


def build_e5_data_provenance_check(
    concerns: tuple[ProvenanceConcern, ...],
    *,
    object_id: str,
    source: SourceLocation,
    materiality: Materiality = Materiality.MAIN_EMPIRICAL_CLAIM,
    finding_id: str = "data_provenance:e5",
) -> CheckResult:
    """Build E5 only from direct verified identity/provenance contradictions.

    E5 means a direct data/provenance concern, not a conclusion about intent or misconduct. Every
    emitted E5 finding is explicitly marked for mandatory human review.
    """

    if not concerns:
        raise ValueError("E5 provenance check requires at least one provenance concern")
    mismatches = tuple(item for item in concerns if item.status is ProvenanceCheckStatus.MISMATCH)
    if not mismatches:
        if any(item.status is ProvenanceCheckStatus.UNVERIFIABLE for item in concerns):
            return CheckResult(
                detector_id="data_provenance_direct_v1",
                check_id="direct_provenance_unverifiable",
                object_id=object_id,
                status=CheckStatus.UNVERIFIABLE,
                family=EvidenceFamily.PROVENANCE,
                message="direct data/provenance evidence is incomplete or unverified",
            )
        return CheckResult(
            detector_id="data_provenance_direct_v1",
            check_id="direct_provenance_match",
            object_id=object_id,
            status=CheckStatus.PASS,
            family=EvidenceFamily.PROVENANCE,
            message="verified direct data/provenance identities are consistent",
        )
    if any(not item.direct_evidence_verified for item in mismatches):
        raise ValueError("E5 requires direct verified provenance evidence for every mismatch")

    evidence = {
        "concerns": [
            {
                "kind": item.kind.value,
                "status": item.status.value,
                "explanation": item.explanation,
                "source": asdict(item.source),
                "evidence_sha256": list(item.evidence_sha256),
            }
            for item in mismatches
        ],
        "human_review_required": True,
        "human_review_status": "pending",
        "intent_inference_authorized": False,
        "production_authorized": False,
    }
    finding = Finding(
        finding_id=finding_id,
        detector_id="data_provenance_direct_v1",
        object_id=object_id,
        grade=EvidenceGrade.DATA_PROVENANCE_CONCERN,
        materiality=materiality,
        family=EvidenceFamily.PROVENANCE,
        title="Direct data/provenance identity conflict requires human review",
        explanation=(
            "Verified artifact, randomization, or sample-lineage identities conflict. This is a "
            "direct provenance concern requiring human review; Veritas does not infer intent, "
            "cause, or misconduct from the conflict."
        ),
        evidence=evidence,
        source=source,
    )
    return CheckResult(
        detector_id="data_provenance_direct_v1",
        check_id="direct_provenance_mismatch",
        object_id=object_id,
        status=CheckStatus.FAIL,
        family=EvidenceFamily.PROVENANCE,
        message="verified direct data/provenance identity mismatch",
        finding=finding,
    )


def _require_sha256(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")
