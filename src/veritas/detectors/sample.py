from __future__ import annotations

from uuid import uuid4

from ..models import CheckResult, Finding, SamplePartition
from ..types import CheckStatus, EvidenceFamily, EvidenceGrade
from .base import Detector


class SampleAccountingDetector(Detector):
    detector_id = "sample_accounting"
    version = "0.1.0"

    def supports(self, obj: object) -> bool:
        return isinstance(obj, SamplePartition)

    def run(self, obj: object) -> list[CheckResult]:
        assert isinstance(obj, SamplePartition)
        if obj.total_n is None or not obj.groups:
            return [CheckResult(
                self.detector_id,
                "partition_arithmetic",
                obj.object_id,
                CheckStatus.UNVERIFIABLE,
                EvidenceFamily.SAMPLE_CONSISTENCY,
                message="Total N and at least one group count are required.",
            )]

        group_sum = sum(obj.groups.values())
        if obj.non_overlapping and group_sum > obj.total_n:
            return [self._failure(obj, "Non-overlapping group counts sum to more than the reported total N.", group_sum)]

        if obj.exhaustive is True:
            if group_sum == obj.total_n:
                return [self._pass(obj, "Exhaustive sample partition matches the reported total N.")]
            return [self._failure(obj, "An exhaustive sample partition does not sum to the reported total N.", group_sum)]

        if group_sum != obj.total_n and obj.explanation_present is False:
            finding = Finding(
                finding_id=f"F-{uuid4().hex[:10]}",
                detector_id=f"{self.detector_id}@{self.version}",
                object_id=obj.object_id,
                grade=EvidenceGrade.WEAK_SIGNAL,
                materiality=obj.materiality,
                family=EvidenceFamily.SAMPLE_CONSISTENCY,
                title="Unexplained sample-count difference",
                explanation="Reported group counts do not equal total N, and no explanation is recorded; the partition is not known to be exhaustive.",
                evidence={"reported_total_n": obj.total_n, "group_sum": group_sum, "groups": obj.groups},
                detector_precision=0.70,
                source=obj.source,
            )
            return [CheckResult(
                self.detector_id,
                "partition_arithmetic",
                obj.object_id,
                CheckStatus.REVIEW,
                EvidenceFamily.SAMPLE_CONSISTENCY,
                message=finding.explanation,
                finding=finding,
            )]

        return [CheckResult(
            self.detector_id,
            "partition_arithmetic",
            obj.object_id,
            CheckStatus.UNVERIFIABLE,
            EvidenceFamily.SAMPLE_CONSISTENCY,
            message="The group counts are not declared to form an exhaustive partition, so unequal totals are not a contradiction.",
        )]

    def _pass(self, obj: SamplePartition, message: str) -> CheckResult:
        return CheckResult(self.detector_id, "partition_arithmetic", obj.object_id, CheckStatus.PASS, EvidenceFamily.SAMPLE_CONSISTENCY, message=message)

    def _failure(self, obj: SamplePartition, explanation: str, group_sum: int) -> CheckResult:
        finding = Finding(
            finding_id=f"F-{uuid4().hex[:10]}",
            detector_id=f"{self.detector_id}@{self.version}",
            object_id=obj.object_id,
            grade=EvidenceGrade.INTERNAL_CONTRADICTION,
            materiality=obj.materiality,
            family=EvidenceFamily.SAMPLE_CONSISTENCY,
            title="Sample arithmetic contradiction",
            explanation=explanation,
            evidence={"reported_total_n": obj.total_n, "group_sum": group_sum, "groups": obj.groups},
            source=obj.source,
        )
        return CheckResult(self.detector_id, "partition_arithmetic", obj.object_id, CheckStatus.FAIL, EvidenceFamily.SAMPLE_CONSISTENCY, message=explanation, finding=finding)
