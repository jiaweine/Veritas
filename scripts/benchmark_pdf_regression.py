from __future__ import annotations

import json
import random
from hashlib import sha256

import pymupdf
from scipy.stats import norm

from veritas.audit import AuditEngine
from veritas.extraction import ConformalCalibration, ConformalExtractionGate
from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import (
    calibration_manifest_sha256,
    extract_regression_table,
    prepare_regression_pdf_audit,
    regression_result_builder,
)
from veritas.types import EvidenceGrade

CASES = 24
STRESS_CASES = 8
SEED = 90210


def make_pdf(beta: str, se: str, z: str, p_value: str, *, layout: str = "grid") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=720 if layout == "journal_wide" else 612, height=792)
    page.insert_text((60, 72), "Synthetic Social Science Article", fontsize=14)
    page.insert_text((60, 112), "Table 2. Main regression", fontsize=11)

    if layout == "journal_wide":
        xs = (60, 210, 300, 390, 470, 535, 605, 690)
        header = ("Variable", "Coefficient", "Standard Error", "z value", "Wald", "P value", "OR")
        data = ("Treatment", beta, se, z, f"{float(z) ** 2:.3f}", p_value, f"{pow(2.718281828, float(beta)):.3f}")
        header_size = 7
    else:
        xs = (72, 220, 300, 380, 460, 540)
        header = ("Variable", "Coef.", "SE", "z", "p")
        data = ("Treatment", beta, se, z, p_value)
        header_size = 9

    ys = (140, 170, 200)
    if layout != "borderless":
        for x in xs:
            page.draw_line((x, ys[0]), (x, ys[-1]), width=0.8)
        for y in ys:
            page.draw_line((xs[0], y), (xs[-1], y), width=0.8)

    for column, text in enumerate(header):
        page.insert_text((xs[column] + 4, 160), text, fontsize=header_size)
    for column, text in enumerate(data):
        page.insert_text((xs[column] + 4, 190), text, fontsize=8 if layout == "journal_wide" else 9)

    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def gate() -> ConformalExtractionGate:
    return ConformalExtractionGate(ConformalCalibration((0.01,) * 100, alpha=0.05), min_independent_families=2)


def audit_pdf(pdf: bytes) -> tuple[bool, bool, bool]:
    snapshots = parse_pdf_dual(pdf)
    bundle = extract_regression_table(snapshots, variable_label="Treatment")
    dual_parse = all(len(bundle.field_candidates[key]) == 2 for key in ("beta", "se", "t_stat", "p_value"))
    ledger, spec = prepare_regression_pdf_audit(
        pdf,
        gate(),
        variable_label="Treatment",
        calibration_sha256=calibration_manifest_sha256(b"synthetic-pdf-regression-calibration-v1"),
    )
    report, envelope = ledger.promote("regression-1", spec, regression_result_builder)
    if envelope is None:
        return dual_parse, False, False
    audit = AuditEngine().audit_verified([envelope])
    hard = any(finding.grade >= EvidenceGrade.INTERNAL_CONTRADICTION for finding in audit.findings)
    return dual_parse, report.hard_audit_ready, hard


def stress_coverage(layout: str) -> dict[str, float]:
    parsed = promoted = 0
    for index in range(STRESS_CASES):
        se = 0.04 + 0.01 * index
        z = 1.4 + 0.2 * index
        beta = se * z
        p = float(2.0 * norm.sf(abs(z)))
        pdf = make_pdf(f"{beta:.3f}", f"{se:.3f}", f"{z:.3f}", f"{p:.3f}", layout=layout)
        dual, promote, _ = audit_pdf(pdf)
        parsed += int(dual)
        promoted += int(promote)
    return {
        f"{layout}_dual_parser_coverage": parsed / STRESS_CASES,
        f"{layout}_promotion_coverage": promoted / STRESS_CASES,
    }


def main() -> None:
    rng = random.Random(SEED)
    parse_ok = 0
    promoted_valid = 0
    valid_false_alerts = 0
    promoted_corrupt = 0
    corrupt_detected = 0
    artifact_hashes: set[str] = set()

    for _ in range(CASES):
        se = rng.choice([0.040, 0.050, 0.060, 0.080, 0.100, 0.120, 0.150, 0.200])
        z = rng.choice([1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8])
        beta = se * z
        p = float(2.0 * norm.sf(abs(z)))
        valid_pdf = make_pdf(f"{beta:.3f}", f"{se:.3f}", f"{z:.3f}", f"{p:.3f}")
        artifact_hashes.add(sha256(valid_pdf).hexdigest())
        dual, promoted, hard = audit_pdf(valid_pdf)
        parse_ok += int(dual)
        promoted_valid += int(promoted)
        valid_false_alerts += int(hard)

        corrupt_pdf = make_pdf(f"{beta:.3f}", f"{se:.3f}", f"{z:.3f}", "0.500")
        artifact_hashes.add(sha256(corrupt_pdf).hexdigest())
        _, corrupt_promoted, corrupt_hard = audit_pdf(corrupt_pdf)
        promoted_corrupt += int(corrupt_promoted)
        corrupt_detected += int(corrupt_hard)

    report = {
        "cases_per_arm": CASES,
        "dual_parser_field_coverage": parse_ok / CASES,
        "valid_promotion_coverage": promoted_valid / CASES,
        "valid_e3_false_alert_rate": valid_false_alerts / CASES,
        "corrupt_promotion_coverage": promoted_corrupt / CASES,
        "corruption_e3_detection_rate": corrupt_detected / CASES,
        "unique_pdf_artifacts": len(artifact_hashes),
        "seed": SEED,
        **stress_coverage("journal_wide"),
        **stress_coverage("borderless"),
    }
    print(json.dumps(report, sort_keys=True))

    if parse_ok != CASES or promoted_valid != CASES or promoted_corrupt != CASES:
        raise SystemExit("native PDF grid parsing/promotion coverage regressed")
    if valid_false_alerts != 0:
        raise SystemExit("valid synthetic PDFs produced E3 false alerts")
    if corrupt_detected != CASES:
        raise SystemExit("obvious p-value corruptions were not all detected")
    if report["journal_wide_dual_parser_coverage"] != 1.0 or report["journal_wide_promotion_coverage"] != 1.0:
        raise SystemExit("journal-style wide tables regressed")
    # Borderless coverage is diagnostic in v0.9 until the independent geometry fallback is calibrated.


if __name__ == "__main__":
    main()
