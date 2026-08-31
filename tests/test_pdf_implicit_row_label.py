from __future__ import annotations

import pymupdf

from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import RegressionLocator, extract_regression_table


def _implicit_label_pdf(*, caption_declares_first_column: bool) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    caption = "Table 2. First column: coefficient name."
    if not caption_declares_first_column:
        caption = "Table 2. Model estimates and inferential statistics."
    page.insert_text((36, 90), caption, fontsize=8)

    headers = (
        (114, "Estimate"),
        (193, "Std. Error"),
        (276, "lower CI"),
        (354, "upper CI"),
        (436, "z value"),
        (515, "Pr(>|z|)"),
    )
    for x, text in headers:
        page.insert_text((x, 125), text, fontsize=8)
    row = (
        (36, "beta"),
        (112, "0.1848905"),
        (191, "0.03399295"),
        (274, "0.1182656"),
        (353, "0.2515155"),
        (436, "5.439085"),
        (511, "5.355501e-08"),
    )
    for x, text in row:
        page.insert_text((x, 150), text, fontsize=8)

    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_implicit_row_label_requires_caption_semantics_and_extracts_both_parsers() -> None:
    snapshots = parse_pdf_dual(
        _implicit_label_pdf(caption_declares_first_column=True),
        artifact_id="implicit-row-label",
    )
    bundle = extract_regression_table(
        snapshots,
        variable_label="beta",
        locator=RegressionLocator(table_label="Table 2", expected_page=1),
    )

    expected = {
        "beta": "0.1848905",
        "se": "0.03399295",
        "t_stat": "5.439085",
        "p_value": "5.355501e-08",
    }
    assert not bundle.ambiguities
    for key, value in expected.items():
        candidates = bundle.field_candidates[key]
        assert len(candidates) == 2
        assert {candidate.normalized_value for candidate in candidates} == {value}
        assert {candidate.nonconformity_score for candidate in candidates} == {0.02}


def test_implicit_row_label_fails_closed_without_caption_semantics() -> None:
    snapshots = parse_pdf_dual(
        _implicit_label_pdf(caption_declares_first_column=False),
        artifact_id="implicit-row-label-negative",
    )
    bundle = extract_regression_table(
        snapshots,
        variable_label="beta",
        locator=RegressionLocator(table_label="Table 2", expected_page=1),
    )

    assert not bundle.ambiguities
    assert all(not candidates for candidates in bundle.field_candidates.values())
