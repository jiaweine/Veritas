"""Veritas: evidence-first auditing for empirical social science research."""

from .audit import AuditEngine
from .models import AuditSummary, CheckResult, Finding, RegressionResult, ReportedNumber, SamplePartition
from .types import EvidenceFamily, EvidenceGrade, Materiality

__all__ = [
    "AuditEngine",
    "AuditSummary",
    "CheckResult",
    "EvidenceFamily",
    "EvidenceGrade",
    "Finding",
    "Materiality",
    "RegressionResult",
    "ReportedNumber",
    "SamplePartition",
]

__version__ = "0.1.0"
