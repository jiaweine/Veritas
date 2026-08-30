from veritas.detectors.algebra import LogitOddsRatioDetector, MediationProductDetector
from veritas.models import LogitResult, MediationResult, ReportedNumber
from veritas.types import CheckStatus, EvidenceGrade


def test_logit_odds_ratio_passes_with_rounding():
    obj = LogitResult(
        object_id="l1",
        beta=ReportedNumber(0.693, decimals=3),
        odds_ratio=ReportedNumber(2.00, decimals=2),
        exp_beta_relation_verified=True,
    )
    result = LogitOddsRatioDetector().run(obj)[0]
    assert result.status is CheckStatus.PASS


def test_logit_odds_ratio_contradiction():
    obj = LogitResult(
        object_id="l2",
        beta=ReportedNumber(0.693, decimals=3),
        odds_ratio=ReportedNumber(1.40, decimals=2),
        exp_beta_relation_verified=True,
    )
    result = LogitOddsRatioDetector().run(obj)[0]
    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION


def test_logit_relation_must_be_verified():
    obj = LogitResult(
        object_id="l3",
        beta=ReportedNumber(0.693, decimals=3),
        odds_ratio=ReportedNumber(1.40, decimals=2),
    )
    result = LogitOddsRatioDetector().run(obj)[0]
    assert result.status is CheckStatus.UNVERIFIABLE


def test_mediation_product_passes_with_rounding():
    obj = MediationResult(
        object_id="m1",
        a_path=ReportedNumber(0.30, decimals=2),
        b_path=ReportedNumber(0.40, decimals=2),
        indirect_effect=ReportedNumber(0.12, decimals=2),
        product_definition_verified=True,
        scale_consistent_verified=True,
    )
    result = MediationProductDetector().run(obj)[0]
    assert result.status is CheckStatus.PASS


def test_mediation_product_contradiction():
    obj = MediationResult(
        object_id="m2",
        a_path=ReportedNumber(0.30, decimals=2),
        b_path=ReportedNumber(0.40, decimals=2),
        indirect_effect=ReportedNumber(0.20, decimals=2),
        product_definition_verified=True,
        scale_consistent_verified=True,
    )
    result = MediationProductDetector().run(obj)[0]
    assert result.status is CheckStatus.FAIL
    assert result.finding is not None
    assert result.finding.grade is EvidenceGrade.INTERNAL_CONTRADICTION
