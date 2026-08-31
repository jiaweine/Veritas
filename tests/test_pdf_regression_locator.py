import pymupdf

from veritas.pdf_native import NativePDFSnapshot, PDFPageSnapshot, PDFTable, parse_pdf_dual
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


def _snapshot(
    parser_id: str,
    parser_family: str,
    rows: tuple[tuple[str | None, ...], ...],
) -> NativePDFSnapshot:
    table = PDFTable(
        page=1,
        table_index=1,
        bbox=(40.0, 80.0, 560.0, 220.0),
        rows=rows,
        caption="Table 2. Main model",
    )
    page = PDFPageSnapshot(
        page=1,
        width=612.0,
        height=792.0,
        words=(),
        blocks=(),
        tables=(table,),
    )
    return NativePDFSnapshot(
        artifact_id="paper",
        artifact_sha256="a" * 64,
        parser_id=parser_id,
        parser_family=parser_family,
        parser_version="test",
        pages=(page,),
    )


def _regression_rows(label: str, values: tuple[str, str, str, str]) -> tuple[tuple[str | None, ...], ...]:
    return (
        ("Independent variable", "β", "SE", "z-value", "p-value"),
        (label, *values),
    )


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


def test_relaxed_token_boundary_join_requires_exact_anchor_and_same_numbers() -> None:
    left = _snapshot(
        "parser_a",
        "family_a",
        _regression_rows("Image: neutral", ("0.104", "0.038", "2.735", "0.006 **")),
    )
    right = _snapshot(
        "parser_b",
        "family_b",
        _regression_rows("Image:neutral", ("0.104", "0.038", "2.735", "0.006**")),
    )

    bundle = extract_regression_table(
        (left, right),
        variable_label="Image: neutral",
        locator=RegressionLocator(table_label="Table 2", expected_page=1),
    )

    assert bundle.ambiguities == ()
    assert [item.normalized_value for item in bundle.field_candidates["beta"]] == ["0.104", "0.104"]
    assert [item.normalized_value for item in bundle.field_candidates["p_value"]] == ["0.006", "0.006"]
    assert {item.parser_family for item in bundle.field_candidates["beta"]} == {"family_a", "family_b"}


def test_whitespace_erasure_cannot_create_row_identity_without_exact_anchor() -> None:
    left = _snapshot(
        "parser_a",
        "family_a",
        _regression_rows("AB", ("0.100", "0.050", "2.000", "0.046")),
    )
    right = _snapshot(
        "parser_b",
        "family_b",
        _regression_rows("AB", ("0.100", "0.050", "2.000", "0.046")),
    )

    bundle = extract_regression_table(
        (left, right),
        variable_label="A B",
        locator=RegressionLocator(table_label="Table 2", expected_page=1),
    )

    assert bundle.ambiguities == ()
    assert all(not candidates for candidates in bundle.field_candidates.values())


def test_relaxed_canonical_collision_is_ambiguous_and_cannot_add_second_family() -> None:
    left = _snapshot(
        "parser_a",
        "family_a",
        _regression_rows("A B", ("0.100", "0.050", "2.000", "0.046")),
    )
    right_rows = (
        ("Independent variable", "β", "SE", "z-value", "p-value"),
        ("AB", "0.100", "0.050", "2.000", "0.046"),
        ("AB", "0.300", "0.050", "6.000", "< 0.001"),
    )
    right = _snapshot("parser_b", "family_b", right_rows)

    bundle = extract_regression_table(
        (left, right),
        variable_label="A B",
        locator=RegressionLocator(table_label="Table 2", expected_page=1),
    )

    assert bundle.ambiguities
    assert len(bundle.field_candidates["beta"]) == 1
    assert bundle.field_candidates["beta"][0].parser_family == "family_a"
