from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import replace
from hashlib import sha256

from .detectors.algebra import LogitOddsRatioDetector, MediationProductDetector
from .detectors.anova import OneWayAnovaSummaryDetector
from .detectors.base import DetectorRegistry
from .detectors.correlation import CorrelationPSDDetector
from .detectors.designs import DIDDesignDetector, WeakIVDesignDetector
from .detectors.discrete import DiscreteSummaryFeasibilityDetector
from .detectors.group_stats import TwoGroupSummaryDetector
from .detectors.meta_analysis import MetaAnalysisArithmeticDetector
from .detectors.rdd import RDDDesignDetector
from .detectors.regression import RegressionConsistencyDetector
from .detectors.sample import SampleAccountingDetector
from .detectors.sem import SEMFitArithmeticDetector, SEMNestedDifferenceDetector
from .detectors.standardized_regression import StandardizedRegressionReconstructionDetector
from .ingestion import DetectorInputEnvelope
from .models import AuditSummary, CheckResult, Finding
from .runtime import numerical_backend_sha256, veritas_source_sha256
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
                    StandardizedRegressionReconstructionDetector(),
                    TwoGroupSummaryDetector(),
                    OneWayAnovaSummaryDetector(),
                    MetaAnalysisArithmeticDetector(),
                    SEMFitArithmeticDetector(),
                    SEMNestedDifferenceDetector(),
                    DIDDesignDetector(),
                    WeakIVDesignDetector(),
                    RDDDesignDetector(),
                ]
            )
        self.registry = DetectorRegistry(detectors)

    def manifest_sha256(self) -> str:
        """Stable identity of Veritas source, detector declarations, and numerical software."""
        payload = {
            "veritas_source_sha256": veritas_source_sha256(),
            "detector_registry_sha256": self.registry.sha256(),
            "numerical_backend_sha256": numerical_backend_sha256(),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()

    def audit(self, objects: Iterable[object]) -> AuditSummary:
        checks: list[CheckResult] = []
        for obj in objects:
            detectors = self.registry.for_object(obj)
            for detector in detectors:
                checks.extend(detector.run(obj))
        return self._summarize(checks)

    def audit_verified(self, envelopes: Iterable[DetectorInputEnvelope]) -> AuditSummary:
        """Run promotion-gated research/benchmark audits without production authority."""
        return self._audit_envelopes(envelopes, production_authorized=False)

    def audit_production_verified(self, envelopes: Iterable[DetectorInputEnvelope]) -> AuditSummary:
        """Run only envelopes certified for this exact Veritas/numerical system manifest."""
        materialized = tuple(envelopes)
        unauthorized = [
            envelope.object_id for envelope in materialized if not envelope.production_authorized
        ]
        if unauthorized:
            raise ValueError(
                "production audit requires PRODUCTION_CERTIFIED calibration with held-out certificate; "
                f"unauthorized object ids: {tuple(unauthorized)!r}"
            )

        current_system = self.manifest_sha256()
        mismatched = [
            envelope.object_id
            for envelope in materialized
            if envelope.certified_system_sha256 != current_system
        ]
        if mismatched:
            raise ValueError(
                "production certificate was issued for a different Veritas/numerical system manifest; "
                f"mismatched object ids: {tuple(mismatched)!r}"
            )
        return self._audit_envelopes(materialized, production_authorized=True)

    def _audit_envelopes(
        self,
        envelopes: Iterable[DetectorInputEnvelope],
        *,
        production_authorized: bool,
    ) -> AuditSummary:
        checks: list[CheckResult] = []
        current_system = self.manifest_sha256()
        for envelope in envelopes:
            obj = envelope.statistical_object
            actual_object_id = getattr(obj, "object_id", None)
            if actual_object_id is not None and str(actual_object_id) != envelope.object_id:
                raise ValueError("DetectorInputEnvelope.object_id does not match the statistical object")
            provenance = {
                "artifact_sha256": envelope.artifact_sha256,
                "ingestion_protocol_sha256": envelope.protocol_sha256,
                "promotion_spec_sha256": envelope.promotion_spec_sha256,
                "extraction_evidence_sha256": envelope.evidence_sha256,
                "calibration_scope": envelope.calibration_scope.value,
                "production_certificate_sha256": envelope.production_certificate_sha256,
                "certified_promotion_spec_sha256": envelope.certified_promotion_spec_sha256,
                "certified_system_sha256": envelope.certified_system_sha256,
                "executed_system_sha256": current_system,
                "production_hard_finding_authorized": production_authorized,
            }
            for detector in self.registry.for_object(obj):
                for check in detector.run(obj):
                    if check.finding is None:
                        checks.append(check)
                        continue
                    finding = replace(
                        check.finding,
                        evidence={**check.finding.evidence, "ingestion_provenance": provenance},
                    )
                    checks.append(replace(check, finding=finding))
        return self._summarize(checks)

    def _summarize(self, checks: list[CheckResult]) -> AuditSummary:
        findings: list[Finding] = [check.finding for check in checks if check.finding is not None]
        return AuditSummary(
            verification_coverage=round(verification_coverage(checks), 4),
            review_priority=review_priority(findings),
            findings=tuple(findings),
            checks=tuple(checks),
        )
