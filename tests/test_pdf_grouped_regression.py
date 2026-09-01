from __future__ import annotations

from veritas.extraction import ConformalCalibration, ConformalExtractionGate
from veritas.ingestion import PromotionDecision
from veritas.pdf_grouped_regression import GroupedRegressionLocator, extract_grouped_regression_table
from veritas.pdf_native import NativePDFSnapshot, PDFPageSnapshot, PDFWord
from veritas.pdf_regression import bundle_to_ledger, regression_promotion_spec, regression_result_builder


def _word(text: str, x: float, y: float, width: float = 24.0) -> PDFWord:
    return PDFWord(page=1, text=text, bbox=(x, y - 1.0, x + width, y + 1.0))


def _snapshot(
    parser_id: str,
    parser_family: str,
    *,
    incomplete_second_block: bool = False,
    subheader_y: float = 110.0,
) -> NativePDFSnapshot:
    data_y = subheader_y + 20.0
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
        _word("Mean", 116, subheader_y, 24),
        _word("(SD)", 144, subheader_y, 24),
        _word("B", 200, subheader_y, 10),
        _word("SE", 240, subheader_y, 14),
        _word("t", 280, subheader_y, 8),
        _word("β", 320, subheader_y, 10),
        _word("p-value", 360, subheader_y, 34),
        _word("B", 410, subheader_y, 10),
        _word("SE", 450, subheader_y, 14),
        _word("t", 490, subheader_y, 8),
    ]
    if not incomplete_second_block:
        words.append(_word("β", 530, subheader_y, 10))
    words.extend(
        [
            _word("p-value", 570, subheader_y, 34),
            _word("Age", 40, data_y, 18),
            _word("<−0.01", 200, data_y, 34),
            _word("0.01", 240, data_y, 22),
            _word("−0.64", 280, data_y, 28),
            _word("−0.03", 320, data_y, 28),
            _word("0.523", 360, data_y, 28),
            _word("0.02", 410, data_y, 22),
            _word("0.01", 450, data_y, 22),
            _word("1.55", 490, data_y, 22),
            _word("0.07", 530, data_y, 22),
            _word("0.123", 570, data_y, 28),
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


def _dual(
    *,
    incomplete_second_block: bool = False,
    subheader_y: float = 110.0,
) -> tuple[NativePDFSnapshot, ...]:
    return (
        _snapshot(
            "pymupdf_native",
            "mupdf_native",
            incomplete_second_block=incomplete_second_block,
            subheader_y=subheader_y,
        ),
        _snapshot(
            "pdfplumber_native",
            "pdfminer_native",
            incomplete_second_block=incomplete_second_block,
            subheader_y=subheader_y,
        ),
    )


def _multivariable_bundle(*, subheader_y: float = 110.0):
    return extract_grouped_regression_table(
        _dual(subheader_y=subheader_y),
        variable_label="Age",
        locator=GroupedRegressionLocator(
            table_label="Table 2",
            model_group_label="Multivariable regression analysis",
            expected_page=1,
        ),
    )


def test_grouped_regression_uses_publication_visible_model_group() -> None:
    bundle = _multivariable_bundle()

    assert not bundle.ambiguities
    assert [candidate.normalized_value for candidate in bundle.field_candidates["beta"]] == ["0.02", "0.02"]
    assert [candidate.normalized_value for candidate in bundle.field_candidates["se"]] == ["0.01", "0.01"]
    assert [candidate.normalized_value for candidate in bundle.field_candidates["t_stat"]] == ["1.55", "1.55"]
    assert [candidate.normalized_value for candidate in bundle.field_candidates["p_value"]] == ["0.123", "0.123"]
    assert all(candidate.parser_family in {"mupdf_native", "pdfminer_native"} for candidate in bundle.field_candidates["beta"])
    assert bundle.semantic_candidates["inference_distribution"] == ()


def test_grouped_regression_accepts_observed_sixteen_point_header_gap() -> None:
    bundle = _multivariable_bundle(subheader_y=116.2)

    assert not bundle.ambiguities
    assert [candidate.normalized_value for candidate in bundle.field_candidates["beta"]] == ["0.02", "0.02"]


def test_grouped_regression_rejects_distant_subheader_even_when_roles_repeat() -> None:
    bundle = _multivariable_bundle(subheader_y=124.0)

    assert not bundle.ambiguities
    assert all(not candidates for candidates in bundle.field_candidates.values())


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


def test_grouped_exact_fields_do_not_bypass_missing_inference_semantics() -> None:
    bundle = _multivariable_bundle()
    gate = ConformalExtractionGate(
        ConformalCalibration(nonconformity_scores=(0.02,) * 40, alpha=0.05)
    )
    ledger = bundle_to_ledger(
        bundle,
        gate,
        calibration_sha256="c" * 64,
        object_id="grouped-regression",
    )
    report, envelope = ledger.promote(
        "grouped-regression",
        regression_promotion_spec(),
        regression_result_builder,
    )

    assert report.decision is PromotionDecision.UNVERIFIABLE
    assert envelope is None
    assert "missing critical semantic gate: inference_distribution" in report.reasons
