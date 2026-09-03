from pathlib import Path


def test_data_preregistration_integrity_docs_lock_review_and_e5_boundaries() -> None:
    text = Path("docs/DATA_PREREGISTRATION_INTEGRITY.md").read_text(encoding="utf-8")

    for phrase in (
        "preregistration, pre-analysis plan (PAP), and registry",
        "invalid mutations are rolled back",
        "not E5 findings by themselves",
        "at least two **independent signal families**",
        "Survey response heuristics never create E5",
        "human_review_required: true",
        "intent_inference_authorized: false",
        "production_authorized: false",
        "does not infer cause, intent, fabrication, falsification, or misconduct",
        "Missing artifacts remain neutral/unverifiable",
    ):
        assert phrase in text
