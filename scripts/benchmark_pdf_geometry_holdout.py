from __future__ import annotations

import json
import random
import statistics
import time
from dataclasses import replace

import pymupdf
from scipy.stats import norm

from veritas.audit import AuditEngine
from veritas.extraction import ConformalCalibration, ConformalExtractionGate
from veritas.ingestion import CalibrationScope
from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import (
    calibration_manifest_sha256,
    extract_regression_table,
    prepare_regression_pdf_audit,
    regression_result_builder,
)
from veritas.types import EvidenceGrade

SEED = 731991
POSITIVE_CASES = 24
NEGATIVE_CASES = 12


def _insert_table(
    page: pymupdf.Page,
    *,
    y: float,
    xs: tuple[float, ...],
    variable: str,
    beta: str,
    se: str,
    z: str,
    p: str,
    caption: str = "Table 4. Regression estimates",
    font_size: float = 8.0,
    split_p: bool = False,
) -> None:
    page.insert_text((xs[0], y - 34), caption, fontsize=font_size + 1.0)
    headers = ("Variable", "Coefficient", "Standard Error", "z value", "P value")
    for index, text in enumerate(headers):
        page.insert_text((xs[index], y), text, fontsize=font_size)
    values = (variable, beta, se, z)
    for index, text in enumerate(values):
        page.insert_text((xs[index], y + 28), text, fontsize=font_size)
    if split_p and p.startswith("<"):
        page.insert_text((xs[4], y + 28), "<", fontsize=font_size)
        page.insert_text((xs[4] + 9, y + 28), p[1:].strip(), fontsize=font_size)
    else:
        page.insert_text((xs[4], y + 28), p, fontsize=font_size)


def _positive_pdf(index: int, *, corrupt: bool = False) -> tuple[bytes, str]:
    rng = random.Random(SEED + index * 10007)
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((48, 48), "Empirical results", fontsize=12)
    variables = (
        "Treatment assignment",
        "Policy exposure",
        "Program participation",
        "Income shock",
    )
    variable = variables[index % len(variables)]
    base_xs = (54.0, 190.0, 286.0, 390.0, 470.0)
    shift = rng.uniform(-8.0, 12.0)
    jitter = (
        0.0,
        rng.uniform(-5.0, 5.0),
        rng.uniform(-4.0, 4.0),
        rng.uniform(-3.0, 3.0),
        rng.uniform(-3.0, 3.0),
    )
    xs = tuple(base + shift + delta for base, delta in zip(base_xs, jitter, strict=True))
    y = 145.0 + rng.uniform(-18.0, 22.0)
    font_size = rng.choice((6.8, 7.2, 8.0, 8.8, 9.4))

    se_value = rng.choice((0.041, 0.052, 0.067, 0.083, 0.114))
    z_value = rng.choice((1.8, 2.1, 2.4, 2.8, 3.4))
    beta_value = se_value * z_value
    true_p = float(2.0 * norm.sf(abs(z_value)))
    p = "0.500" if corrupt else ("< .001" if true_p < 0.001 else f"{true_p:.3f}")
    caption = rng.choice(
        ("Table 4. Regression estimates", "TABLE 2 Logistic regression", "Table A1. Main model")
    )
    _insert_table(
        page,
        y=y,
        xs=xs,
        variable=variable,
        beta=f"{beta_value:.3f}",
        se=f"{se_value:.3f}",
        z=f"{z_value:.3f}",
        p=p,
        caption=caption,
        font_size=font_size,
        split_p=index % 3 == 0,
    )

    if index % 4 == 0:
        page.insert_text((555, y), "Notes", fontsize=6.5)
        page.insert_text((555, y + 28), "robust", fontsize=6.5)
    if index % 5 == 0:
        _insert_table(
            page,
            y=y + 235,
            xs=xs,
            variable="Placebo outcome",
            beta="0.010",
            se="0.020",
            z="0.500",
            p="0.617",
            caption="Table 5. Placebo model",
            font_size=font_size,
        )
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload, variable


def _negative_pdf(index: int) -> tuple[bytes, str]:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    xs = (54.0, 190.0, 286.0, 390.0, 470.0)
    variable = "Treatment assignment"
    y = 150.0
    mode = index % 4
    if mode == 0:
        page.insert_text((54, 80), "Notation used in the examples", fontsize=11)
        page.insert_text((54, y - 34), "Regression notation", fontsize=9)
        headers = ("Variable", "Coefficient", "Standard Error", "z value", "P value")
        values = (variable, "0.120", "0.050", "2.400", "0.016")
        for column, text in enumerate(headers):
            page.insert_text((xs[column], y), text, fontsize=8)
        for column, text in enumerate(values):
            page.insert_text((xs[column], y + 28), text, fontsize=8)
    elif mode == 1:
        _insert_table(
            page,
            y=y,
            xs=xs,
            variable="Control variable",
            beta="0.120",
            se="0.050",
            z="2.400",
            p="0.016",
        )
        page.insert_text((xs[0], 590), variable, fontsize=8)
        for column, text in enumerate(("0.120", "0.050", "2.400", "0.016"), start=1):
            page.insert_text((xs[column], 590), text, fontsize=8)
    elif mode == 2:
        page.insert_text((54, y - 34), "Table 3. Descriptive coefficients", fontsize=9)
        headers = ("Variable", "Coefficient", "Standard Error", "P value")
        values = (variable, "0.120", "0.050", "0.016")
        for column, text in enumerate(headers):
            page.insert_text((xs[column], y), text, fontsize=8)
        for column, text in enumerate(values):
            page.insert_text((xs[column], y + 28), text, fontsize=8)
    else:
        _insert_table(
            page,
            y=y,
            xs=xs,
            variable="Different exposure",
            beta="0.120",
            se="0.050",
            z="2.400",
            p="0.016",
        )
    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload, variable


def _synthetic_geometry_gate() -> ConformalExtractionGate:
    calibration = ConformalCalibration((0.02,) * 200, alpha=0.05)
    return ConformalExtractionGate(calibration, min_independent_families=2)


def _audit(
    pdf: bytes,
    variable: str,
    *,
    gate: ConformalExtractionGate,
) -> tuple[bool, bool, bool, bool, float]:
    started = time.perf_counter()
    snapshots = parse_pdf_dual(pdf)
    bundle = extract_regression_table(snapshots, variable_label=variable)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    fields = ("beta", "se", "t_stat", "p_value")
    dual = all(len(bundle.field_candidates[key]) == 2 for key in fields)
    exact = dual and all(
        len({candidate.normalized_value for candidate in bundle.field_candidates[key]}) == 1
        for key in fields
    )
    if not exact:
        return dual, False, False, False, elapsed_ms
    ledger, spec = prepare_regression_pdf_audit(
        pdf,
        gate,
        variable_label=variable,
        calibration_sha256=calibration_manifest_sha256(b"synthetic-geometry-holdout-v1"),
    )
    ledger.protocol = replace(
        ledger.protocol,
        calibration_scope=CalibrationScope.BENCHMARK,
    )
    report, envelope = ledger.promote("regression-1", spec, regression_result_builder)
    if envelope is None:
        return dual, False, False, False, elapsed_ms
    audit = AuditEngine().audit_verified([envelope])
    hard = any(
        finding.grade >= EvidenceGrade.INTERNAL_CONTRADICTION
        for finding in audit.findings
    )
    return dual, report.detector_ready, hard, envelope.production_authorized, elapsed_ms


def main() -> None:
    gate = _synthetic_geometry_gate()
    valid_dual = valid_promoted = valid_false_alerts = 0
    corrupt_dual = corrupt_promoted = corrupt_detected = 0
    production_authorized = 0
    negative_false_extractions = 0
    latencies: list[float] = []
    corrupt_failures: list[int] = []

    for index in range(POSITIVE_CASES):
        pdf, variable = _positive_pdf(index, corrupt=False)
        dual, promoted, hard, authorized, elapsed = _audit(pdf, variable, gate=gate)
        valid_dual += int(dual)
        valid_promoted += int(promoted)
        valid_false_alerts += int(hard)
        production_authorized += int(authorized)
        latencies.append(elapsed)

        corrupt_pdf, corrupt_variable = _positive_pdf(index, corrupt=True)
        corrupt_is_dual, corrupt_is_promoted, corrupt_hard, corrupt_authorized, elapsed = _audit(
            corrupt_pdf,
            corrupt_variable,
            gate=gate,
        )
        corrupt_dual += int(corrupt_is_dual)
        corrupt_promoted += int(corrupt_is_promoted)
        corrupt_detected += int(corrupt_hard)
        production_authorized += int(corrupt_authorized)
        if not (corrupt_is_dual and corrupt_is_promoted and corrupt_hard):
            corrupt_failures.append(index)
        latencies.append(elapsed)

    for index in range(NEGATIVE_CASES):
        pdf, variable = _negative_pdf(index)
        snapshots = parse_pdf_dual(pdf)
        bundle = extract_regression_table(snapshots, variable_label=variable)
        if any(bundle.field_candidates.values()):
            negative_false_extractions += 1

    report = {
        "seed": SEED,
        "positive_cases_per_arm": POSITIVE_CASES,
        "negative_cases": NEGATIVE_CASES,
        "heldout_dual_parser_coverage": valid_dual / POSITIVE_CASES,
        "synthetic_geometry_detector_promotion_coverage": valid_promoted / POSITIVE_CASES,
        "valid_e3_false_alert_rate": valid_false_alerts / POSITIVE_CASES,
        "corrupt_dual_parser_coverage": corrupt_dual / POSITIVE_CASES,
        "corrupt_detector_promotion_coverage": corrupt_promoted / POSITIVE_CASES,
        "obvious_p_corruption_e3_detection_rate": corrupt_detected / POSITIVE_CASES,
        "benchmark_production_hard_authority_coverage": production_authorized / (2 * POSITIVE_CASES),
        "corrupt_failure_indices": corrupt_failures,
        "negative_false_extraction_rate": negative_false_extractions / NEGATIVE_CASES,
        "median_dual_parse_ms": round(statistics.median(latencies), 2),
        "calibration_scope": CalibrationScope.BENCHMARK.value,
        "corruption_design": "paired_same_layout_only_p_cell_changed",
    }
    print(json.dumps(report, sort_keys=True))

    if valid_dual != POSITIVE_CASES or corrupt_dual != POSITIVE_CASES:
        raise SystemExit("held-out borderless dual-parser coverage is below 100%")
    if valid_promoted != POSITIVE_CASES or corrupt_promoted != POSITIVE_CASES:
        raise SystemExit("synthetic geometry calibration failed to promote a supported held-out table to detector")
    if production_authorized != 0:
        raise SystemExit("synthetic geometry benchmark acquired production hard authority")
    if valid_false_alerts:
        raise SystemExit("held-out valid borderless tables produced E3 false alerts")
    if corrupt_detected != POSITIVE_CASES:
        raise SystemExit("held-out obvious p-value corruptions were not all detected")
    if negative_false_extractions:
        raise SystemExit("geometry fallback extracted one or more adversarial negative layouts")


if __name__ == "__main__":
    main()
