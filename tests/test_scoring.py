from veritas.models import CheckResult, Finding
from veritas.scoring import review_priority, verification_coverage
from veritas.types import CheckStatus, EvidenceFamily, EvidenceGrade, Materiality


def test_unverifiable_reduces_coverage_not_priority():
    checks = [
        CheckResult("d", "a", "x", CheckStatus.PASS, EvidenceFamily.NUMERICAL_CONSISTENCY),
        CheckResult("d", "b", "x", CheckStatus.UNVERIFIABLE, EvidenceFamily.DATA_INTEGRITY),
    ]
    assert verification_coverage(checks) == 0.5
    assert review_priority([]) == 0.0


def test_same_family_does_not_double_count():
    base = {
        "detector_id": "d@1",
        "object_id": "x",
        "grade": EvidenceGrade.INTERNAL_CONTRADICTION,
        "materiality": Materiality.MAIN_EMPIRICAL_CLAIM,
        "family": EvidenceFamily.NUMERICAL_CONSISTENCY,
        "title": "x",
        "explanation": "x",
    }
    one = Finding(finding_id="F1", **base)
    two = Finding(finding_id="F2", **base)
    assert review_priority([one]) == review_priority([one, two])
