from veritas.detectors.discrete import DiscreteSummaryFeasibilityDetector
from veritas.models import DiscreteSummary, ReportedNumber
from veritas.types import CheckStatus, EvidenceGrade


def _summary(*, n, mean, mean_decimals, sd=None, sd_decimals=None, weighted=False):
    return DiscreteSummary(
        object_id="d1",
        n=n,
        mean=ReportedNumber(mean, decimals=mean_decimals),
        sd=ReportedNumber(sd, decimals=sd_decimals) if sd is not None else None,
        sd_definition="sample" if sd is not None else "unknown",
        support=(1.0, 2.0, 3.0, 4.0, 5.0),
        support_verified=True,
        n_verified=True,
        weighted=weighted,
    )


def test_discrete_mean_feasible():
    result = DiscreteSummaryFeasibilityDetector().run(
        _summary(n=5, mean=3.0, mean_decimals=2)
    )[0]
    assert result.status is CheckStatus.PASS


def test_discrete_mean_infeasible_is_capped_at_e2():
    result = DiscreteSummaryFeasibilityDetector().run(
        _summary(n=4, mean=3.14, mean_decimals=2)
    )[0]
    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.METHODOLOGICAL_RISK
    assert result.finding.evidence["severity_ceiling"] == "E2 until AuditBench certification"


def test_discrete_mean_and_sd_feasible():
    # The sample [1, 2, 3, 4, 5] has mean 3 and sample SD sqrt(2.5) ~= 1.5811.
    result = DiscreteSummaryFeasibilityDetector().run(
        _summary(n=5, mean=3.0, mean_decimals=2, sd=1.58, sd_decimals=2)
    )[0]
    assert result.status is CheckStatus.PASS


def test_discrete_mean_and_sd_infeasible():
    result = DiscreteSummaryFeasibilityDetector().run(
        _summary(n=5, mean=3.0, mean_decimals=2, sd=0.01, sd_decimals=2)
    )[0]
    assert result.status is CheckStatus.FAIL


def test_weighting_unknown_abstains():
    result = DiscreteSummaryFeasibilityDetector().run(
        _summary(n=5, mean=3.0, mean_decimals=2, weighted=None)
    )[0]
    assert result.status is CheckStatus.UNVERIFIABLE
