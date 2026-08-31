import json
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parents[1] / "benchmark" / "extraction" / "seed_cases_v0.11.json"


def test_real_extraction_seed_has_required_identity_and_review_boundaries():
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert payload["status"] == "seed_corpus_not_locked_gold"
    assert payload["production_hard_finding_authorized"] is False

    cases = payload["cases"]
    case_ids = [case["case_id"] for case in cases]
    assert len(case_ids) == len(set(case_ids))
    assert len(cases) >= 4

    required_fields = {"beta", "se", "t_stat", "p_value"}
    for case in cases:
        assert case["paper_id"]
        assert case["article_family_id"]
        assert case["pdf_url"].startswith("https://")
        assert case["license_note"]
        assert case["object_type"]
        assert case["split"] is None
        assert case["review_status"] == "legacy_manual_check_pending_two_independent_reviewers"
        locator = case["locator"]
        assert locator["expected_page"] > 0
        assert locator["table_label"]
        assert locator["row_label"]
        assert set(case["expected_fields"]) == required_fields
