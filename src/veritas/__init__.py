"""Veritas: evidence-first auditing for empirical social science research."""

from .audit import AuditEngine
from .claims import (
    ArtifactRef,
    ClaimEdge,
    ClaimNode,
    ClaimRole,
    ExtractedField,
    RelationType,
    StatisticalClaimGraph,
    StatisticalObjectNode,
)
from .methodology import MethodAnchor, get_method_anchor, methodology_snapshot_sha256
from .models import (
    AuditSummary,
    CheckResult,
    CorrelationMatrix,
    DIDDesign,
    Finding,
    IVDesign,
    RDDDesign,
    RegressionResult,
    ReportedNumber,
    SamplePartition,
    SourceLocation,
)
from .types import EvidenceFamily, EvidenceGrade, Materiality

__all__ = [
    "ArtifactRef",
    "AuditEngine",
    "AuditSummary",
    "CheckResult",
    "ClaimEdge",
    "ClaimNode",
    "ClaimRole",
    "CorrelationMatrix",
    "DIDDesign",
    "EvidenceFamily",
    "EvidenceGrade",
    "ExtractedField",
    "Finding",
    "IVDesign",
    "Materiality",
    "MethodAnchor",
    "RDDDesign",
    "RegressionResult",
    "RelationType",
    "ReportedNumber",
    "SamplePartition",
    "SourceLocation",
    "StatisticalClaimGraph",
    "StatisticalObjectNode",
    "get_method_anchor",
    "methodology_snapshot_sha256",
]

__version__ = "0.2.0"
