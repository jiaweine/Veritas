from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256

from scipy.stats import beta as beta_distribution

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BenchmarkSplit(str, Enum):
    TRAIN = "train"
    DEVELOPMENT = "development"
    TEST = "test"


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    paper_id: str
    corruption_family: str
    expected_material_issue: bool
    split: BenchmarkSplit
    metadata: dict[str, object]


@dataclass(frozen=True)
class PaperAuditOutcome:
    paper_id: str
    expected_material_issue: bool
    hard_alert: bool
    applicable: bool = True


@dataclass(frozen=True)
class CertificationPolicy:
    confidence: float = 0.95
    max_false_hard_alert_upper_bound: float = 0.01
    min_hard_alert_precision_lower_bound: float = 0.95
    min_clean_papers: int = 300
    min_positive_papers: int = 50


@dataclass(frozen=True)
class CertificationReport:
    clean_papers: int
    positive_papers: int
    false_hard_alerts: int
    true_hard_alerts: int
    missed_positive_papers: int
    false_hard_alert_rate: float
    false_hard_alert_upper_bound: float
    hard_alert_precision: float
    hard_alert_precision_lower_bound: float
    recall: float
    certified: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProductionCalibrationCertificate:
    """Deterministic provenance artifact for a calibration certified on held-out papers.

    This is an auditable hash-bound certificate, not a cryptographic signature or external trust
    service. It binds a calibration to the exact TEST benchmark manifest, audited detector/system
    manifest, certification policy, and resulting paper-level certification report.
    """

    calibration_sha256: str
    benchmark_manifest_sha256: str
    audited_system_sha256: str
    policy_sha256: str
    certification_report_sha256: str
    clean_papers: int
    positive_papers: int
    false_hard_alert_upper_bound: float
    hard_alert_precision_lower_bound: float
    certificate_version: str = "1"

    def __post_init__(self) -> None:
        for name, value in (
            ("calibration_sha256", self.calibration_sha256),
            ("benchmark_manifest_sha256", self.benchmark_manifest_sha256),
            ("audited_system_sha256", self.audited_system_sha256),
            ("policy_sha256", self.policy_sha256),
            ("certification_report_sha256", self.certification_report_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        if self.clean_papers < 0 or self.positive_papers < 0:
            raise ValueError("certificate paper counts cannot be negative")
        for name, value in (
            ("false_hard_alert_upper_bound", self.false_hard_alert_upper_bound),
            ("hard_alert_precision_lower_bound", self.hard_alert_precision_lower_bound),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if not self.certificate_version.strip():
            raise ValueError("certificate_version is required")

    def sha256(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()


def assign_paper_split(
    paper_id: str,
    *,
    salt: str,
    train_fraction: float = 0.60,
    development_fraction: float = 0.20,
) -> BenchmarkSplit:
    """Assign all cases from one paper to one deterministic split to prevent leakage."""
    if train_fraction <= 0 or development_fraction <= 0 or train_fraction + development_fraction >= 1:
        raise ValueError("split fractions must leave positive mass for the test split")
    digest = sha256(f"{salt}:{paper_id}".encode()).digest()
    value = int.from_bytes(digest[:8], "big") / float(2**64)
    if value < train_fraction:
        return BenchmarkSplit.TRAIN
    if value < train_fraction + development_fraction:
        return BenchmarkSplit.DEVELOPMENT
    return BenchmarkSplit.TEST


def benchmark_manifest_sha256(cases: tuple[BenchmarkCase, ...] | list[BenchmarkCase]) -> str:
    payload = [
        {
            **asdict(case),
            "split": case.split.value,
        }
        for case in sorted(cases, key=lambda case: case.case_id)
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def certification_policy_sha256(policy: CertificationPolicy) -> str:
    raw = json.dumps(asdict(policy), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def certification_report_sha256(report: CertificationReport) -> str:
    raw = json.dumps(asdict(report), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def binomial_upper_bound(successes: int, trials: int, *, confidence: float = 0.95) -> float:
    """One-sided exact Clopper-Pearson upper bound for a binomial rate."""
    _validate_binomial(successes, trials, confidence)
    if trials == 0:
        return 1.0
    if successes == trials:
        return 1.0
    return float(beta_distribution.ppf(confidence, successes + 1, trials - successes))


def binomial_lower_bound(successes: int, trials: int, *, confidence: float = 0.95) -> float:
    """One-sided exact Clopper-Pearson lower bound for a binomial rate."""
    _validate_binomial(successes, trials, confidence)
    if trials == 0 or successes == 0:
        return 0.0
    if successes == trials:
        return float(beta_distribution.ppf(1.0 - confidence, successes, 1))
    return float(beta_distribution.ppf(1.0 - confidence, successes, trials - successes + 1))


def evaluate_hard_alert_certification(
    outcomes: tuple[PaperAuditOutcome, ...] | list[PaperAuditOutcome],
    policy: CertificationPolicy | None = None,
) -> CertificationReport:
    """Evaluate E3+ readiness using paper-level errors and exact uncertainty bounds.

    Multiple findings within one paper count once. This prevents a detector from
    appearing statistically stronger by producing many correlated alerts from a
    single underlying error.
    """
    policy = policy or CertificationPolicy()
    applicable = [outcome for outcome in outcomes if outcome.applicable]
    clean = [outcome for outcome in applicable if not outcome.expected_material_issue]
    positive = [outcome for outcome in applicable if outcome.expected_material_issue]

    false_alerts = sum(outcome.hard_alert for outcome in clean)
    true_alerts = sum(outcome.hard_alert for outcome in positive)
    missed = len(positive) - true_alerts
    total_alerts = false_alerts + true_alerts

    false_rate = false_alerts / len(clean) if clean else 0.0
    false_upper = binomial_upper_bound(false_alerts, len(clean), confidence=policy.confidence)
    precision = true_alerts / total_alerts if total_alerts else 0.0
    precision_lower = binomial_lower_bound(true_alerts, total_alerts, confidence=policy.confidence)
    recall = true_alerts / len(positive) if positive else 0.0

    reasons: list[str] = []
    if len(clean) < policy.min_clean_papers:
        reasons.append(f"need at least {policy.min_clean_papers} clean applicable papers")
    if len(positive) < policy.min_positive_papers:
        reasons.append(f"need at least {policy.min_positive_papers} positive applicable papers")
    if false_upper > policy.max_false_hard_alert_upper_bound:
        reasons.append(
            "paper-level false hard-alert upper confidence bound exceeds policy: "
            f"{false_upper:.4f} > {policy.max_false_hard_alert_upper_bound:.4f}"
        )
    if precision_lower < policy.min_hard_alert_precision_lower_bound:
        reasons.append(
            "hard-alert precision lower confidence bound is below policy: "
            f"{precision_lower:.4f} < {policy.min_hard_alert_precision_lower_bound:.4f}"
        )

    return CertificationReport(
        clean_papers=len(clean),
        positive_papers=len(positive),
        false_hard_alerts=false_alerts,
        true_hard_alerts=true_alerts,
        missed_positive_papers=missed,
        false_hard_alert_rate=false_rate,
        false_hard_alert_upper_bound=false_upper,
        hard_alert_precision=precision,
        hard_alert_precision_lower_bound=precision_lower,
        recall=recall,
        certified=not reasons,
        reasons=tuple(reasons),
    )


def issue_production_calibration_certificate(
    *,
    calibration_sha256: str,
    audited_system_sha256: str,
    cases: tuple[BenchmarkCase, ...] | list[BenchmarkCase],
    outcomes: tuple[PaperAuditOutcome, ...] | list[PaperAuditOutcome],
    policy: CertificationPolicy | None = None,
) -> tuple[CertificationReport, ProductionCalibrationCertificate | None]:
    """Issue a production certificate only from a fully held-out, paper-consistent TEST corpus."""
    for name, value in (
        ("calibration_sha256", calibration_sha256),
        ("audited_system_sha256", audited_system_sha256),
    ):
        if not _SHA256_RE.fullmatch(value):
            raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    if not cases:
        raise ValueError("production certification requires at least one benchmark case")
    if any(case.split is not BenchmarkSplit.TEST for case in cases):
        raise ValueError("production certification may only use TEST-split benchmark cases")

    expected_by_paper: dict[str, bool] = {}
    for case in cases:
        expected_by_paper[case.paper_id] = expected_by_paper.get(case.paper_id, False) or case.expected_material_issue

    if len({outcome.paper_id for outcome in outcomes}) != len(outcomes):
        raise ValueError("production certification requires one paper-level outcome per paper")
    outcome_by_paper = {outcome.paper_id: outcome for outcome in outcomes}
    if set(outcome_by_paper) != set(expected_by_paper):
        raise ValueError("paper ids in certification outcomes must exactly match the TEST benchmark manifest")
    inconsistent = [
        paper_id
        for paper_id, expected in expected_by_paper.items()
        if outcome_by_paper[paper_id].expected_material_issue != expected
    ]
    if inconsistent:
        raise ValueError(
            "paper-level expected-material-issue labels disagree with benchmark cases: "
            f"{tuple(sorted(inconsistent))!r}"
        )

    policy = policy or CertificationPolicy()
    report = evaluate_hard_alert_certification(list(outcomes), policy)
    if not report.certified:
        return report, None

    certificate = ProductionCalibrationCertificate(
        calibration_sha256=calibration_sha256,
        benchmark_manifest_sha256=benchmark_manifest_sha256(list(cases)),
        audited_system_sha256=audited_system_sha256,
        policy_sha256=certification_policy_sha256(policy),
        certification_report_sha256=certification_report_sha256(report),
        clean_papers=report.clean_papers,
        positive_papers=report.positive_papers,
        false_hard_alert_upper_bound=report.false_hard_alert_upper_bound,
        hard_alert_precision_lower_bound=report.hard_alert_precision_lower_bound,
    )
    return report, certificate


def _validate_binomial(successes: int, trials: int, confidence: float) -> None:
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("require 0 <= successes <= trials")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
