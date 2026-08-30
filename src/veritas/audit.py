from __future__ import annotations

from collections.abc import Iterable

from .detectors.base import DetectorRegistry
from .detectors.regression import RegressionConsistencyDetector
from .detectors.sample import SampleAccountingDetector
from .models import AuditSummary, CheckResult, Finding
from .scoring import review_priority, verification_coverage


class AuditEngine:
    def __init__(self, registry: DetectorRegistry | None = None) -> None:
        self.registry = registry or DetectorRegistry([
            RegressionConsistencyDetector(),
            SampleAccountingDetector(),
        ])

    def audit(self, objects: Iterable[object]) -> AuditSummary:
        checks: list[CheckResult] = []
        for obj in objects:
            detectors = self.registry.for_object(obj)
            for detector in detectors:
                checks.extend(detector.run(obj))
        findings: list[Finding] = [check.finding for check in checks if check.finding is not None]
        return AuditSummary(
            verification_coverage=round(verification_coverage(checks), 4),
            review_priority=review_priority(findings),
            findings=tuple(findings),
            checks=tuple(checks),
        )
