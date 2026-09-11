from __future__ import annotations

import pymupdf

from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import RegressionLocator, _header_role, extract_regression_table


def _combined_cell_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((54, 70), "Table 2. Interaction model", fontsize=10)
    xs = (54.0, 210.0, 340.0, 430.0, 510.0, 580.0)
    ys = (105.0, 136.0, 168.0)
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), width=0.7)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), width=0.7)
    headers = ("Variable", "Coefficient (SE)", "t-value", "p-value", "95% CI")
    values = ("F01 (Group male vs. female)", "-0.028** (0.010)", "-2.80", "0.005", "[-0.047, -0.008]")
    for index, text in enumerate(headers):
        page.insert_text((xs[index] + 3, 126), text, fontsize=7)
    for index, text in enumerate(values):
        page.insert_text((xs[index] + 3, 157), text, fontsize=7)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_combined_coefficient_se_header_has_explicit_compound_role() -> None:
    assert _header_role("Coefficient (SE)") == "beta_se"
    assert _header_role("Estimate (SE)") == "beta_se"


def test_combined_coefficient_se_cell_splits_deterministically_across_parsers() -> None:
    snapshots = parse_pdf_dual(_combined_cell_pdf())
    bundle = extract_regression_table(
        snapshots,
        variable_label="F01 (Group male vs. female)",
        locator=RegressionLocator(table_label="Table 2", expected_page=1),
    )

    assert not bundle.ambiguities
    assert {item.normalized_value for item in bundle.field_candidates["beta"]} == {"-0.028"}
    assert {item.normalized_value for item in bundle.field_candidates["se"]} == {"0.010"}
    assert {item.normalized_value for item in bundle.field_candidates["t_stat"]} == {"-2.80"}
    assert {item.normalized_value for item in bundle.field_candidates["p_value"]} == {"0.005"}
    assert all(len(bundle.field_candidates[key]) == 2 for key in ("beta", "se", "t_stat", "p_value"))
    assert bundle.semantic_candidates["inference_distribution"] == ()
