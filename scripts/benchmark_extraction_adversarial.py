from __future__ import annotations

import json

import pymupdf

from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import extract_regression_table

_REQUIRED_FIELDS = ("beta", "se", "t_stat", "p_value")


def _insert_table(
    page: pymupdf.Page,
    *,
    caption: str,
    y: float,
    variable: str,
    beta: str,
    se: str,
    statistic: str,
    p_value: str,
    panel_label: str | None = None,
) -> None:
    xs = (54.0, 205.0, 300.0, 395.0, 475.0)
    page.insert_text((54, y - 42), caption, fontsize=9)
    if panel_label is not None:
        page.insert_text((54, y - 22), panel_label, fontsize=8)
    headers = ("Variable", "Coefficient", "Standard Error", "z value", "P value")
    values = (variable, beta, se, statistic, p_value)
    for index, text in enumerate(headers):
        page.insert_text((xs[index], y), text, fontsize=8)
    for index, text in enumerate(values):
        page.insert_text((xs[index], y + 28), text, fontsize=8)


def _pdf_repeated_label() -> tuple[bytes, str]:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    variable = "Treatment assignment"
    _insert_table(
        page,
        caption="Table 1. Baseline model",
        y=135,
        variable=variable,
        beta="0.120",
        se="0.050",
        statistic="2.400",
        p_value="0.016",
    )
    _insert_table(
        page,
        caption="Table 2. Adjusted model",
        y=360,
        variable=variable,
        beta="0.080",
        se="0.050",
        statistic="1.600",
        p_value="0.110",
    )
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload, variable


def _pdf_continuation_without_parent_identity() -> tuple[bytes, str]:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    variable = "Policy exposure"
    _insert_table(
        page,
        caption="Table 4. Main model",
        y=135,
        variable=variable,
        beta="0.120",
        se="0.050",
        statistic="2.400",
        p_value="0.016",
    )
    _insert_table(
        page,
        caption="Table 4 (continued)",
        y=360,
        variable=variable,
        beta="0.180",
        se="0.060",
        statistic="3.000",
        p_value="0.003",
    )
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload, variable


def _pdf_multi_panel_duplicate_row() -> tuple[bytes, str]:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    variable = "Program participation"
    _insert_table(
        page,
        caption="Table 6. Heterogeneous effects",
        panel_label="Panel A. Urban sample",
        y=150,
        variable=variable,
        beta="0.150",
        se="0.050",
        statistic="3.000",
        p_value="0.003",
    )
    _insert_table(
        page,
        caption="Table 6. Heterogeneous effects",
        panel_label="Panel B. Rural sample",
        y=390,
        variable=variable,
        beta="0.050",
        se="0.050",
        statistic="1.000",
        p_value="0.317",
    )
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload, variable


def _pdf_footnote_pollution() -> tuple[bytes, str]:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    variable = "Income shock"
    _insert_table(
        page,
        caption="Table 3. Main estimates",
        y=150,
        variable=variable,
        beta="0.120a",
        se="0.050",
        statistic="2.400",
        p_value="0.016",
    )
    page.insert_text((54, 250), "a Robustness specification; not part of the coefficient.", fontsize=7)
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload, variable


def _pdf_ocr_like_corruption() -> tuple[bytes, str]:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    variable = "Treatment intensity"
    _insert_table(
        page,
        caption="Table A2. OCR stress case",
        y=150,
        variable=variable,
        beta="O.120",
        se="0.O50",
        statistic="2.4OO",
        p_value="O.016",
    )
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload, variable


def _full_detector_input_ready(pdf: bytes, variable: str) -> tuple[bool, dict[str, object]]:
    snapshots = parse_pdf_dual(pdf)
    bundle = extract_regression_table(snapshots, variable_label=variable)
    counts = {key: len(bundle.field_candidates[key]) for key in _REQUIRED_FIELDS}
    dual_complete = all(counts[key] >= 2 for key in _REQUIRED_FIELDS)
    parser_families = {
        key: sorted({candidate.parser_family for candidate in bundle.field_candidates[key]})
        for key in _REQUIRED_FIELDS
    }
    independent_complete = all(len(parser_families[key]) >= 2 for key in _REQUIRED_FIELDS)
    ready = dual_complete and independent_complete and not bundle.ambiguities
    return ready, {
        "field_candidate_counts": counts,
        "parser_families": parser_families,
        "ambiguities": bundle.ambiguities,
    }


def main() -> None:
    cases = (
        ("repeated-row-label-across-displays", "repeated_label", _pdf_repeated_label),
        (
            "continuation-table-without-parent-identity",
            "continuation_table",
            _pdf_continuation_without_parent_identity,
        ),
        ("multi-panel-duplicate-row-label", "multi_panel", _pdf_multi_panel_duplicate_row),
        ("footnote-number-near-estimate", "footnote_pollution", _pdf_footnote_pollution),
        ("ocr-like-character-confusion", "ocr_like_corruption", _pdf_ocr_like_corruption),
    )
    results: list[dict[str, object]] = []
    unsafe: list[str] = []
    for case_id, family, builder in cases:
        pdf, variable = builder()
        ready, evidence = _full_detector_input_ready(pdf, variable)
        if ready:
            unsafe.append(case_id)
        results.append(
            {
                "case_id": case_id,
                "family": family,
                "passed": not ready,
                "unsafe_full_detector_input_ready": ready,
                **evidence,
            }
        )

    report = {
        "scope": "synthetic_adversarial_extraction_fail_closed",
        "cases": len(cases),
        "passed": len(cases) - len(unsafe),
        "unsafe_case_ids": unsafe,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if unsafe:
        raise SystemExit("one or more adversarial extraction cases formed unsafe full detector input")


if __name__ == "__main__":
    main()
