from __future__ import annotations

import json
from pathlib import Path

from veritas.types import CheckStatus, EvidenceGrade

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "benchmark/auditbench/v02_pack_cases.json"
LOCK = ROOT / "benchmark/auditbench/v02_pack_lock.json"
PROTOCOL = ROOT / "benchmark/auditbench/v1_protocol.json"

_REQUIRED_DETECTORS = {
    "discrete_summary_feasibility",
    "logit_odds_ratio_consistency",
    "mediation_product_consistency",
    "sem_fit_arithmetic",
}


def _cases() -> list[dict[str, object]]:
    return json.loads(CASES.read_text(encoding="utf-8"))["cases"]


def test_v02_pack_covers_every_remaining_issue_3_detector_family():
    detector_ids = {str(case["detector_id"]) for case in _cases()}
    assert detector_ids == _REQUIRED_DETECTORS


def test_discrete_infeasibility_remains_capped_at_e2():
    by_case = {str(case["case_id"]): case for case in _cases()}
    case = by_case["discrete-mean-infeasible"]
    assert case["expected_status"] == CheckStatus.FAIL.value
    assert case["maximum_allowed_grade"] == EvidenceGrade.METHODOLOGICAL_RISK.name


def test_direct_arithmetic_contradictions_are_the_only_e3_cases_in_pack():
    e3_cases = {
        str(case["case_id"])
        for case in _cases()
        if case["maximum_allowed_grade"] == EvidenceGrade.INTERNAL_CONTRADICTION.name
    }
    assert e3_cases == {
        "logit-or-contradiction",
        "mediation-product-contradiction",
        "sem-cfi-contradiction",
    }


def test_unresolved_semantics_fail_closed():
    by_case = {str(case["case_id"]): case for case in _cases()}
    for case_id in (
        "discrete-weighting-unresolved",
        "logit-relation-unresolved",
        "mediation-scale-unresolved",
        "sem-rmsea-convention-unresolved",
        "sem-robust-formula-unresolved",
    ):
        case = by_case[case_id]
        assert case["expected_status"] == CheckStatus.UNVERIFIABLE.value
        assert case["maximum_allowed_grade"] == EvidenceGrade.UNVERIFIABLE.name
        assert case["extraction_error_case"] is True


def test_v02_lock_reuses_production_denial_protocol():
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert lock["protocol_sha256"] == (
        "2f681e1fc73dcb0ea7901f1c8e6b84139b72c2a050cd6429daae3f41d7c56e4b"
    )
    assert protocol["governance"]["synthetic_ci_results_are_not_production_certification"] is True
    assert protocol["governance"]["production_e3_requires_external_benchmark_evidence"] is True
