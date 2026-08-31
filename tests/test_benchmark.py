import pytest

from veritas.benchmark import (
    BenchmarkCase,
    BenchmarkSplit,
    CertificationPolicy,
    PaperAuditOutcome,
    assign_paper_split,
    benchmark_manifest_sha256,
    binomial_upper_bound,
    evaluate_hard_alert_certification,
    issue_production_calibration_certificate,
)


def test_paper_split_prevents_case_level_leakage():
    split_a = assign_paper_split("paper-1", salt="locked-v1")
    split_b = assign_paper_split("paper-1", salt="locked-v1")

    assert split_a is split_b


def test_manifest_hash_is_order_invariant():
    cases = [
        BenchmarkCase("c2", "p2", "sample", False, BenchmarkSplit.TEST, {}),
        BenchmarkCase("c1", "p1", "pvalue", True, BenchmarkSplit.TEST, {}),
    ]

    assert benchmark_manifest_sha256(cases) == benchmark_manifest_sha256(list(reversed(cases)))


def test_zero_false_alerts_still_need_enough_clean_papers():
    assert binomial_upper_bound(0, 100, confidence=0.95) > 0.01
    assert binomial_upper_bound(0, 400, confidence=0.95) < 0.01


def test_certification_passes_only_with_tight_uncertainty_bounds():
    outcomes = [PaperAuditOutcome(f"clean-{i}", False, False) for i in range(400)]
    outcomes.extend(PaperAuditOutcome(f"positive-{i}", True, True) for i in range(100))
    policy = CertificationPolicy(min_clean_papers=300, min_positive_papers=50)

    report = evaluate_hard_alert_certification(outcomes, policy)

    assert report.certified
    assert report.false_hard_alert_upper_bound < 0.01
    assert report.hard_alert_precision_lower_bound > 0.95


def test_single_false_alert_can_block_strict_certification():
    outcomes = [PaperAuditOutcome(f"clean-{i}", False, i == 0) for i in range(400)]
    outcomes.extend(PaperAuditOutcome(f"positive-{i}", True, True) for i in range(100))

    report = evaluate_hard_alert_certification(outcomes)

    assert not report.certified
    assert report.reasons


def _certification_corpus() -> tuple[list[BenchmarkCase], list[PaperAuditOutcome]]:
    cases = [
        BenchmarkCase(
            case_id=f"clean-case-{i}",
            paper_id=f"clean-{i}",
            corruption_family="none",
            expected_material_issue=False,
            split=BenchmarkSplit.TEST,
            metadata={},
        )
        for i in range(400)
    ]
    cases.extend(
        BenchmarkCase(
            case_id=f"positive-case-{i}",
            paper_id=f"positive-{i}",
            corruption_family="p_value_override",
            expected_material_issue=True,
            split=BenchmarkSplit.TEST,
            metadata={},
        )
        for i in range(100)
    )
    outcomes = [PaperAuditOutcome(f"clean-{i}", False, False) for i in range(400)]
    outcomes.extend(PaperAuditOutcome(f"positive-{i}", True, True) for i in range(100))
    return cases, outcomes


def test_production_certificate_binds_calibration_test_manifest_and_system():
    cases, outcomes = _certification_corpus()
    report, certificate = issue_production_calibration_certificate(
        calibration_sha256="a" * 64,
        audited_system_sha256="b" * 64,
        cases=cases,
        outcomes=outcomes,
    )

    assert report.certified
    assert certificate is not None
    assert certificate.calibration_sha256 == "a" * 64
    assert certificate.audited_system_sha256 == "b" * 64
    assert certificate.benchmark_manifest_sha256 == benchmark_manifest_sha256(cases)
    assert certificate.clean_papers == 400
    assert certificate.positive_papers == 100
    assert len(certificate.sha256()) == 64


def test_production_certificate_rejects_non_test_cases():
    cases, outcomes = _certification_corpus()
    first = cases[0]
    cases[0] = BenchmarkCase(
        case_id=first.case_id,
        paper_id=first.paper_id,
        corruption_family=first.corruption_family,
        expected_material_issue=first.expected_material_issue,
        split=BenchmarkSplit.DEVELOPMENT,
        metadata=first.metadata,
    )

    with pytest.raises(ValueError, match="TEST-split"):
        issue_production_calibration_certificate(
            calibration_sha256="a" * 64,
            audited_system_sha256="b" * 64,
            cases=cases,
            outcomes=outcomes,
        )


def test_production_certificate_rejects_manifest_outcome_label_mismatch():
    cases, outcomes = _certification_corpus()
    outcomes[0] = PaperAuditOutcome("clean-0", True, False)

    with pytest.raises(ValueError, match="expected-material-issue"):
        issue_production_calibration_certificate(
            calibration_sha256="a" * 64,
            audited_system_sha256="b" * 64,
            cases=cases,
            outcomes=outcomes,
        )


def test_failed_certification_never_issues_certificate():
    cases = [
        BenchmarkCase(
            case_id=f"case-{i}",
            paper_id=f"paper-{i}",
            corruption_family="none",
            expected_material_issue=False,
            split=BenchmarkSplit.TEST,
            metadata={},
        )
        for i in range(20)
    ]
    outcomes = [PaperAuditOutcome(f"paper-{i}", False, False) for i in range(20)]

    report, certificate = issue_production_calibration_certificate(
        calibration_sha256="a" * 64,
        audited_system_sha256="b" * 64,
        cases=cases,
        outcomes=outcomes,
    )

    assert not report.certified
    assert certificate is None
