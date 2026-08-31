import pymupdf

from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import RegressionLocator, extract_regression_table


def _two_table_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    xs = (60, 220, 310, 390, 470)

    def add_table(y: float, caption: str, values: tuple[str, ...]) -> None:
        page.insert_text((60, y - 32), caption, fontsize=9)
        for x, text in zip(xs, ("Variable", "Coef.", "SE", "z", "p"), strict=True):
            page.insert_text((x, y), text, fontsize=8)
        for x, text in zip(xs, values, strict=True):
            page.insert_text((x, y + 28), text, fontsize=8)

    add_table(130, "Table 1. Baseline model", ("Treatment", "0.100", "0.050", "2.000", "0.046"))
    add_table(340, "Table 2. Main model", ("Treatment", "0.200", "0.050", "4.000", "< 0.001"))
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def test_same_variable_across_display_items_fails_closed_without_locator() -> None:
    snapshots = parse_pdf_dual(_two_table_pdf())
    bundle = extract_regression_table(snapshots, variable_label="Treatment")

    assert bundle.ambiguities
    assert all(not candidates for candidates in bundle.field_candidates.values())


def test_publication_table_locator_selects_requested_display_item() -> None:
    snapshots = parse_pdf_dual(_two_table_pdf())
    bundle = extract_regression_table(
        snapshots,
        variable_label="Treatment",
        locator=RegressionLocator(table_label="Table 2", expected_page=1),
    )

    assert bundle.ambiguities == ()
    assert [item.normalized_value for item in bundle.field_candidates["beta"]] == ["0.200", "0.200"]
    assert [item.normalized_value for item in bundle.field_candidates["se"]] == ["0.050", "0.050"]
    assert [item.normalized_value for item in bundle.field_candidates["t_stat"]] == ["4.000", "4.000"]
    assert [item.normalized_value for item in bundle.field_candidates["p_value"]] == ["<0.001", "<0.001"]
    assert all("Table 2" in str(item.source.table) for item in bundle.field_candidates["beta"])
