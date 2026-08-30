import random
from statistics import mean, stdev

from veritas.detectors.discrete import DiscreteSummaryFeasibilityDetector
from veritas.models import DiscreteSummary, ReportedNumber
from veritas.types import CheckStatus


def _reported(value: float, decimals: int = 2) -> ReportedNumber:
    return ReportedNumber(float(f"{value:.{decimals}f}"), decimals=decimals)


def test_constructive_samples_never_hard_flag():
    rng = random.Random(20260831)
    detector = DiscreteSummaryFeasibilityDetector(per_solve_time_limit=2.0)
    supports = [
        (-2.0, -1.0, 0.0, 1.0, 2.0),
        (1.0, 2.0, 3.0, 4.0, 5.0),
        (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0),
        (0.0, 0.25, 0.5, 0.75, 1.0),
    ]

    for case_id in range(24):
        support = supports[case_id % len(supports)]
        n = rng.randint(4, 24)
        sample = [rng.choice(support) for _ in range(n)]
        obj = DiscreteSummary(
            object_id=f"constructive-{case_id}",
            n=n,
            mean=_reported(mean(sample)),
            sd=_reported(stdev(sample)),
            sd_definition="sample",
            support=support,
            support_verified=True,
            n_verified=True,
            weighted=False,
        )
        result = detector.run(obj)[0]
        assert result.status is CheckStatus.PASS, (case_id, sample, result.message)
