from __future__ import annotations

import pymupdf

from veritas.extraction import ConformalCalibration, ConformalExtractionGate
from veritas.ingestion import PromotionDecision
from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import (
    RegressionLocator,
    bundle_to_ledger,
    extract_regression_table,
    regression_promotion_spec,
    regression_result_builder,
)


def _borderless_regression_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 90), "Table 2. Borderless regression output", fontsize=10)
    xs = (72, 220, 300, 380, 460)
    for index, text in enumerate(("Variable", "Coef.", "SE", "z", "p")):
        page.insert_text((xs[index], 125), text, fontsize=9)
    for index, text in enumerate(("Treatment", "0.180", "0.060", "3.000", "0.003")):
        page.insert_text((xs[index], 150), text, fontsize=9)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _gate(threshold_score: float) -> ConformalExtractionGate:
    return ConformalExtractionGate(
        ConformalCalibration(nonconformity_scores=(threshold_score,) * 40, alpha=0.05)
    )


def test_borderless_realistic_table_requires_geometry_calibration_for_hard_promotion() -> None:
    snapshots = parse_pdf_dual(_borderless_regression_pdf(), artifact_id="borderless-calibration")
    bundle = extract_regression_table(
        snapshots,
        variable_label="Treatment",
        locator=RegressionLocator(table_label="Table 2", expected_page=1),
    )

    for key in ("beta", "se", "t_stat", "p_value"):
        candidates = bundle.field_candidates[key]
        assert len(candidates) == 2
        assert {candidate.nonconformity_score for candidate in candidates} == {0.02}

    conservative = bundle_to_ledger(
        bundle,
        _gate(0.01),
        calibration_sha256="a" * 64,
        object_id="regression-conservative",
    )
    conservative_report, conservative_envelope = conservative.promote(
        "regression-conservative",
        regression_promotion_spec(),
        regression_result_builder,
    )
    assert conservative_report.decision is PromotionDecision.UNVERIFIABLE
    assert conservative_envelope is None

    geometry_calibrated = bundle_to_ledger(
        bundle,
        _gate(0.02),
        calibration_sha256="b" * 64,
        object_id="regression-geometry",
    )
    geometry_report, geometry_envelope = geometry_calibrated.promote(
        "regression-geometry",
        regression_promotion_spec(),
        regression_result_builder,
    )
    assert geometry_report.decision is PromotionDecision.PROMOTE
    assert geometry_envelope is not None
