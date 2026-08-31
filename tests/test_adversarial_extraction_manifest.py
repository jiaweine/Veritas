import json
from pathlib import Path


MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmark"
    / "extraction"
    / "adversarial_negatives_v0.11.json"
)


def test_adversarial_negative_manifest_covers_required_failure_families():
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert payload["status"] == "adversarial_contract_not_locked_gold"
    assert payload["production_hard_finding_authorized"] is False

    cases = payload["cases"]
    case_ids = [case["case_id"] for case in cases]
    assert len(case_ids) == len(set(case_ids))

    families = {case["family"] for case in cases}
    assert {
        "repeated_label",
        "continuation_table",
        "multi_panel",
        "footnote_pollution",
        "ocr_like_corruption",
    } <= families

    for case in cases:
        assert case["expected_decision"] == "non_accept"
        assert case["required_behavior"]
        assert case["fixture_kind"] in {"synthetic_layout", "synthetic_text_corruption"}
