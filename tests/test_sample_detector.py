from veritas.detectors.sample import SampleAccountingDetector
from veritas.models import SamplePartition
from veritas.types import CheckStatus, EvidenceGrade, Materiality


def test_exhaustive_partition_mismatch_is_contradiction():
    obj = SamplePartition(
        object_id="sample-main",
        total_n=1119,
        groups={"treatment": 521, "control": 498},
        exhaustive=True,
        materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
    )
    check = SampleAccountingDetector().run(obj)[0]
    assert check.status is CheckStatus.FAIL
    assert check.finding is not None
    assert check.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_non_exhaustive_mismatch_is_not_hard_failure():
    obj = SamplePartition(
        object_id="sample-subgroups",
        total_n=1000,
        groups={"treated": 300, "control": 400},
        exhaustive=None,
        explanation_present=False,
    )
    check = SampleAccountingDetector().run(obj)[0]
    assert check.status is CheckStatus.REVIEW
    assert check.finding is not None
    assert check.finding.grade is EvidenceGrade.WEAK_SIGNAL
