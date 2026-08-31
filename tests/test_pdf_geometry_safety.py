from __future__ import annotations

import pymupdf

from veritas.pdf_geometry import reconstruct_borderless_tables
from veritas.pdf_native import NativePDFSnapshot, PDFPageSnapshot, PDFWord, parse_pdf_dual
from veritas.pdf_regression import _header_role, extract_regression_table


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


def _word(text: str, x: float, y: float, *, width: float = 28.0) -> PDFWord:
    return PDFWord(page=1, text=text, bbox=(x, y - 1.0, x + width, y + 1.0))


def _split_header_snapshot(*, beta_y: float) -> NativePDFSnapshot:
    words = (
        _word("Table", 40, 100, width=25),
        _word("2.", 68, 100, width=10),
        _word("Split", 82, 100, width=20),
        _word("header", 105, 100, width=30),
        _word("Variable", 40, 120, width=36),
        _word("Std.Error", 150, 120, width=38),
        _word("z-value", 220, 120, width=30),
        _word("p-value", 280, 120, width=30),
        _word("βi", 100, beta_y, width=10),
        _word("EDTR", 40, 150, width=24),
        _word("0.3596", 100, 150, width=28),
        _word("0.1386", 150, 150, width=28),
        _word("2.5938", 220, 150, width=28),
        _word("0.0095", 280, 150, width=28),
    )
    page = PDFPageSnapshot(
        page=1,
        width=612.0,
        height=792.0,
        words=words,
        blocks=(),
        tables=(),
    )
    return NativePDFSnapshot(
        artifact_id="paper",
        artifact_sha256="a" * 64,
        parser_id="geometry_test",
        parser_family="geometry_test_family",
        parser_version="test",
        pages=(page,),
    )


def test_geometry_does_not_promote_uncaptioned_prose_like_alignment():
    snapshots = parse_pdf_dual(_pdf_with_prose_like_alignment(include_table_caption=False))
    bundle = extract_regression_table(snapshots, variable_label="Treatment")
    assert all(not candidates for candidates in bundle.field_candidates.values())


def test_geometry_rejects_target_row_far_below_header_even_with_caption():
    snapshots = parse_pdf_dual(_pdf_with_prose_like_alignment(include_table_caption=True, far_apart=True))
    bundle = extract_regression_table(snapshots, variable_label="Treatment")
    assert all(not candidates for candidates in bundle.field_candidates.values())


def test_geometry_combines_only_adjacent_bounded_header_lines() -> None:
    tables = reconstruct_borderless_tables(
        _split_header_snapshot(beta_y=126.0),
        variable_label="EDTR",
        role_resolver=_header_role,
        table_label="Table 2",
        allow_token_boundary=False,
    )

    assert len(tables) == 1
    assert tables[0].rows[0][:5] == ("Variable", "βi", "Std.Error", "z-value", "p-value")
    assert tables[0].rows[1][:5] == ("EDTR", "0.3596", "0.1386", "2.5938", "0.0095")


def test_geometry_does_not_borrow_beta_outside_header_band() -> None:
    tables = reconstruct_borderless_tables(
        _split_header_snapshot(beta_y=134.0),
        variable_label="EDTR",
        role_resolver=_header_role,
        table_label="Table 2",
        allow_token_boundary=False,
    )

    assert tables == ()
