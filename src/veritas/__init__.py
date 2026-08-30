"""Veritas: evidence-first auditing for empirical social science research."""

from .audit import AuditEngine
from .benchmark import (
    BenchmarkCase,
    BenchmarkSplit,
    CertificationPolicy,
    CertificationReport,
    PaperAuditOutcome,
    assign_paper_split,
    benchmark_manifest_sha256,
    evaluate_hard_alert_certification,
)
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
from .extraction import (
    ConformalCalibration,
    ConformalExtractionGate,
    ExtractionCandidate,
    ExtractionDecision,
    ExtractionResolution,
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
from .specifications import (
    Specification,
    SpecificationConstraint,
    SpecificationEstimate,
    SpecificationRobustnessSummary,
    SpecificationSpace,
    summarize_specification_robustness,
)
from .types import EvidenceFamily, EvidenceGrade, Materiality

__all__ = [
    "ArtifactRef",
    "AuditEngine",
    "AuditSummary",
    "BenchmarkCase",
    "BenchmarkSplit",
    "CertificationPolicy",
    "CertificationReport",
    "CheckResult",
    "ClaimEdge",
    "ClaimNode",
    "ClaimRole",
    "ConformalCalibration",
    "ConformalExtractionGate",
    "CorrelationMatrix",
    "DIDDesign",
    "EvidenceFamily",
    "EvidenceGrade",
    "ExtractedField",
    "ExtractionCandidate",
    "ExtractionDecision",
    "ExtractionResolution",
    "Finding",
    "IVDesign",
    "Materiality",
    "MethodAnchor",
    "PaperAuditOutcome",
    "RDDDesign",
    "RegressionResult",
    "RelationType",
    "ReportedNumber",
    "SamplePartition",
    "SourceLocation",
    "Specification",
    "SpecificationConstraint",
    "SpecificationEstimate",
    "SpecificationRobustnessSummary",
    "SpecificationSpace",
    "StatisticalClaimGraph",
    "StatisticalObjectNode",
    "assign_paper_split",
    "benchmark_manifest_sha256",
    "evaluate_hard_alert_certification",
    "get_method_anchor",
    "methodology_snapshot_sha256",
    "summarize_specification_robustness",
]

__version__ = "0.2.0"
