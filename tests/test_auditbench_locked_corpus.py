from __future__ import annotations

import json
from pathlib import Path

from veritas.types import CheckStatus, EvidenceGrade

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "benchmark/auditbench/v1_cases.json"

_FRONTIER_DETECTORS = {
    "correlation_psd_sdp",
    "did_design_frontier",
    "rdd_design_frontier",
    "standardized_regression_mccormick_sdp",
    "weak_iv_frontier",
}
_DESIGN_DETECTORS = {
    "did_design_frontier",
    "rdd_design_frontier",
    "weak_iv_frontier",
}


def _cases() -> list[dict[str, object]]:
    payload = json.loads(CASES.read_text(encoding="utf-8"))
    return payload["cases"]


def test_locked_corpus_covers_frontier_detector_families():
    detector_ids = {str(case["detector_id"]) for case in _cases()}
    assert _FRONTIER_DETECTORS <= detector_ids


def test_design_frontier_cases_never_expect_hard_findings():
    design_cases = [
        case for case in _cases() if str(case["detector_id"]) in _DESIGN_DETECTORS
    ]
    assert design_cases
    assert {str(case["expected_status"]) for case in design_cases} >= {
        CheckStatus.PASS.value,
        CheckStatus.REVIEW.value,
        CheckStatus.UNVERIFIABLE.value,
    }
    for case in design_cases:
        assert case["expected_status"] != CheckStatus.FAIL.value
        assert (
            EvidenceGrade[str(case["maximum_allowed_grade"])]
            <= EvidenceGrade.METHODOLOGICAL_RISK
        )


def test_frontier_corpus_locks_direct_hard_and_fail_closed_controls():
    by_case = {str(case["case_id"]): case for case in _cases()}
    assert by_case["corr-out-of-range"]["expected_status"] == CheckStatus.FAIL.value
    assert (
        by_case["corr-out-of-range"]["maximum_allowed_grade"]
        == EvidenceGrade.INTERNAL_CONTRADICTION.name
    )
    for case_id in (
        "std-beta-sample-unresolved",
        "did-semantics-unresolved",
        "iv-counts-unresolved",
        "rdd-framework-unresolved",
    ):
        assert by_case[case_id]["expected_status"] == CheckStatus.UNVERIFIABLE.value
        assert by_case[case_id]["extraction_error_case"] is True
