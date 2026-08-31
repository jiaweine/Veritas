from __future__ import annotations

import pymupdf

from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import extract_regression_table


def _pdf_with_prose_like_alignment(*, include_table_caption: bool, far_apart: bool = False) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Methods and notation", fontsize=14)
    if include_table_caption:
        page.insert_text((72, 112), "Table 3. Regression coefficients", fontsize=10)
    else:
        page.insert_text((72, 112), "The following notation is used in examples.", fontsize=10)

    xs = (72, 220, 300, 380, 460)
    header_y = 150
    data_y = 190 if not far_apart else 520
    for index, text in enumerate(("Variable", "Coef.", "SE", "z", "p")):
        page.insert_text((xs[index], header_y), text, fontsize=9)
    for index, text in enumerate(("Treatment", "0.180", "0.060", "3.000", "0.003")):
        page.insert_text((xs[index], data_y), text, fontsize=9)

    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_geometry_does_not_promote_uncaptioned_prose_like_alignment():
    snapshots = parse_pdf_dual(_pdf_with_prose_like_alignment(include_table_caption=False))
    bundle = extract_regression_table(snapshots, variable_label="Treatment")
    assert all(not candidates for candidates in bundle.field_candidates.values())


def test_geometry_rejects_target_row_far_below_header_even_with_caption():
    snapshots = parse_pdf_dual(_pdf_with_prose_like_alignment(include_table_caption=True, far_apart=True))
    bundle = extract_regression_table(snapshots, variable_label="Treatment")
    assert all(not candidates for candidates in bundle.field_candidates.values())
