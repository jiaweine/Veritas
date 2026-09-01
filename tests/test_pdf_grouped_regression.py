from __future__ import annotations

from veritas.pdf_grouped_regression import GroupedRegressionLocator, extract_grouped_regression_table
from veritas.pdf_native import NativePDFSnapshot, PDFPageSnapshot, PDFWord


def _word(text: str, x: float, y: float, width: float = 24.0) -> PDFWord:
    return PDFWord(page=1, text=text, bbox=(x, y - 1.0, x + width, y + 1.0))


def _snapshot(parser_id: str, parser_family: str, *, incomplete_second_block: bool = False) -> NativePDFSnapshot:
    words = [
        _word("Table", 40, 80, 26),
        _word("2", 70, 80, 8),
        _word("Regression", 84, 80, 48),
        _word("analysis", 136, 80, 34),
        _word("predicting", 174, 80, 42),
        _word("knowledge", 220, 80, 42),
        _word("Variables", 40, 100, 38),
        _word("Overall", 116, 100, 34),
        _word("Bivariable", 194, 100, 48),
        _word("regression", 246, 100, 46),
        _word("analysis", 296, 100, 36),
        _word("Multivariable", 390, 100, 58),
        _word("regression", 452, 100, 46),
        _word("analysis", 502, 100, 36),
        _word("Mean", 116, 110, 24),
        _word("(SD)", 144, 110, 24),
        _word("B", 200, 110, 10),
        _word("SE", 240, 110, 14),
        _word("t", 280, 110, 8),
        _word("β", 320, 110, 10),
        _word("p-value", 360, 110, 34),
        _word("B", 410, 110, 10),
        _word("SE", 450, 110, 14),
        _word("t", 490, 110, 8),
    ]
    if not incomplete_second_block:
        words.append(_word("β", 530, 110, 10))
    words.extend(
        [
            _word("p-value", 570, 110, 34),
            _word("Age", 40, 130, 18),
            _word("<−0.01", 200, 130, 34),
            _word("0.01", 240, 130, 22),
            _word("−0.64", 280, 130, 28),
            _word("−0.03", 320, 130, 28),
            _word("0.523", 360, 130, 28),
            _word("0.02", 410, 130, 22),
            _word("0.01", 450, 130, 22),
            _word("1.55", 490, 130, 22),
            _word("0.07", 530, 130, 22),
            _word("0.123", 570, 130, 28),
        ]
    )
    page = PDFPageSnapshot(
        page=1,
        width=612.0,
        height=792.0,
        words=tuple(words),
        blocks=(),
        tables=(),
    )
    return NativePDFSnapshot(
        artifact_id="paper",
        artifact_sha256="b" * 64,
        parser_id=parser_id,
        parser_family=parser_family,
        parser_version="test",
        pages=(page,),
    )


def _dual(*, incomplete_second_block: bool = False) -> tuple[NativePDFSnapshot, ...]:
    return (
        _snapshot("pymupdf_native", "mupdf_native", incomplete_second_block=incomplete_second_block),
        _snapshot("pdfplumber_native", "pdfminer_native", incomplete_second_block=incomplete_second_block),
    )


def test_grouped_regression_uses_publication_visible_model_group() -> None:
    bundle = extract_grouped_regression_table(
        _dual(),
        variable_label="Age",
        locator=GroupedRegressionLocator(
            table_label="Table 2",
            model_group_label="Multivariable regression analysis",
            expected_page=1,
        ),
    )

    assert not bundle.ambiguities
    assert [candidate.normalized_value for candidate in bundle.field_candidates["beta"]] == ["0.02", "0.02"]
    assert [candidate.normalized_value for candidate in bundle.field_candidates["se"]] == ["0.01", "0.01"]
    assert [candidate.normalized_value for candidate in bundle.field_candidates["t_stat"]] == ["1.55", "1.55"]
    assert [candidate.normalized_value for candidate in bundle.field_candidates["p_value"]] == ["0.123", "0.123"]
    assert all(candidate.parser_family in {"mupdf_native", "pdfminer_native"} for candidate in bundle.field_candidates["beta"])
    assert bundle.semantic_candidates["inference_distribution"] == ()


def test_grouped_regression_distinguishes_unstandardized_b_from_standardized_beta() -> None:
    bundle = extract_grouped_regression_table(
        _dual(),
        variable_label="Age",
        locator=GroupedRegressionLocator(
            table_label="Table 2",
            model_group_label="Bivariable regression analysis",
            expected_page=1,
        ),
    )

    assert [candidate.normalized_value for candidate in bundle.field_candidates["beta"]] == ["<-0.01", "<-0.01"]
    assert "-0.03" not in {candidate.normalized_value for candidate in bundle.field_candidates["beta"]}


def test_grouped_regression_abstains_when_requested_group_is_not_visible() -> None:
    bundle = extract_grouped_regression_table(
        _dual(),
        variable_label="Age",
        locator=GroupedRegressionLocator(
            table_label="Table 2",
            model_group_label="Adjusted model",
            expected_page=1,
        ),
    )

    assert not bundle.ambiguities
    assert all(not candidates for candidates in bundle.field_candidates.values())


def test_grouped_regression_fails_closed_when_group_and_role_blocks_do_not_map_one_to_one() -> None:
    bundle = extract_grouped_regression_table(
        _dual(incomplete_second_block=True),
        variable_label="Age",
        locator=GroupedRegressionLocator(
            table_label="Table 2",
            model_group_label="Multivariable regression analysis",
            expected_page=1,
        ),
    )

    assert bundle.ambiguities
    assert all(not candidates for candidates in bundle.field_candidates.values())
