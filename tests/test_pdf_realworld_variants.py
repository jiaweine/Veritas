from __future__ import annotations

import pymupdf

from veritas.extraction import ConformalCalibration, ConformalExtractionGate
from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import (
    calibration_manifest_sha256,
    extract_regression_table,
    parse_reported_number,
    prepare_regression_pdf_audit,
    regression_result_builder,
)
from veritas.types import CheckStatus, ComparisonOperator


def _journal_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=720, height=792)
    page.insert_text((60, 70), "Table 2. Multivariate logistic regression analysis", fontsize=11)
    xs = (60, 220, 310, 400, 480, 550, 620, 700)
    ys = (110, 140, 170)
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), width=0.7)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), width=0.7)
    header = ("Variable", "Coefficient", "Standard Error", "z value", "Wald", "P value", "OR")
    data = ("Age", "-0.016", "0.004", "-3.650", "13.321", "< 0.001", "0.985")
    for index, text in enumerate(header):
        page.insert_text((xs[index] + 3, 130), text, fontsize=7)
    for index, text in enumerate(data):
        page.insert_text((xs[index] + 3, 160), text, fontsize=8)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _gate() -> ConformalExtractionGate:
    return ConformalExtractionGate(ConformalCalibration((0.01,) * 50, alpha=0.05))


def test_unicode_math_minus_and_inequality_normalization():
    negative = parse_reported_number("−0.016")
    assert negative.value == -0.016
    assert negative.decimals == 3
    assert negative.operator is ComparisonOperator.EQ

    p_value = parse_reported_number("≤ 0.001")
    assert p_value.value == 0.001
    assert p_value.operator is ComparisonOperator.LE


def test_journal_z_value_header_is_extracted_by_both_native_parsers():
    snapshots = parse_pdf_dual(_journal_pdf())
    bundle = extract_regression_table(snapshots, variable_label="Age")
    assert {item.normalized_value for item in bundle.field_candidates["beta"]} == {"-0.016"}
    assert {item.normalized_value for item in bundle.field_candidates["p_value"]} == {"<0.001"}
    assert len(bundle.semantic_candidates["inference_distribution"]) == 2


def test_journal_style_row_promotes_without_guessing_method_semantics():
    ledger, spec = prepare_regression_pdf_audit(
        _journal_pdf(),
        _gate(),
        variable_label="Age",
        calibration_sha256=calibration_manifest_sha256(b"journal-variant-calibration"),
    )
    report, envelope = ledger.promote("regression-1", spec, regression_result_builder)
    assert report.hard_audit_ready
    assert envelope is not None
    # z is explicit in the header, so the method gate is supported rather than guessed.
    assert envelope.statistical_object.inference_distribution == "normal"

    from veritas.audit import AuditEngine

    results = AuditEngine().audit_verified([envelope]).checks
    assert all(item.status is not CheckStatus.UNVERIFIABLE for item in results if item.check_id == "p_value")
