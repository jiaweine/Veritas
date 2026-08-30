from __future__ import annotations

from collections.abc import Iterable

from .detectors.algebra import LogitOddsRatioDetector, MediationProductDetector
from .detectors.base import DetectorRegistry
from .detectors.correlation import CorrelationPSDDetector
from .detectors.designs import DIDDesignDetector, WeakIVDesignDetector
from .detectors.discrete import DiscreteSummaryFeasibilityDetector
from .detectors.rdd import RDDDesignDetector
from .detectors.regression import RegressionConsistencyDetector
from .detectors.sample import SampleAccountingDetector
from .models import AuditSummary, CheckResult, Finding
from .scoring import review_priority, verification_coverage


class AuditEngine:
    def __init__(self, registry: DetectorRegistry | None = None, *, include_experimental: bool = False) -> None:
        if registry is not None:
            self.registry = registry
            return

        detectors = [RegressionConsistencyDetector(), SampleAccountingDetector()]
        if include_experimental:
            detectors.extend(
                [
                    CorrelationPSDDetector(),
                    DiscreteSummaryFeasibilityDetector(),
                    LogitOddsRatioDetector(),
                    MediationProductDetector(),
                    DIDDesignDetector(),
                    WeakIVDesignDetector(),
                    RDDDesignDetector(),
                ]
            )
        self.registry = DetectorRegistry(detectors)

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
