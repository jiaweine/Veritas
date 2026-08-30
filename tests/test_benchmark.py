from veritas.benchmark import (
    BenchmarkCase,
    BenchmarkSplit,
    CertificationPolicy,
    PaperAuditOutcome,
    assign_paper_split,
    benchmark_manifest_sha256,
    binomial_upper_bound,
    evaluate_hard_alert_certification,
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
