from __future__ import annotations

from hashlib import sha256

import pymupdf

from veritas.audit import AuditEngine
from veritas.extraction import ConformalCalibration, ConformalExtractionGate
from veritas.pdf_native import PDFPlumberNativeParser, PyMuPDFNativeParser, parse_pdf_dual
from veritas.pdf_regression import (
    calibration_manifest_sha256,
    extract_regression_table,
    prepare_regression_pdf_audit,
    regression_result_builder,
)
from veritas.types import EvidenceGrade


def _regression_pdf(*, p_value: str = "0.003", beta: str = "0.180", se: str = "0.060", z: str = "3.000") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Synthetic Empirical Study", fontsize=14)
    page.insert_text((72, 112), "Table 1. Regression results", fontsize=11)

    xs = (72, 220, 300, 380, 460, 540)
    ys = (140, 170, 200)
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), width=0.8)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), width=0.8)

    header = ("Variable", "Coef.", "SE", "z", "p")
    data = ("Treatment", beta, se, z, p_value)
    for column, text in enumerate(header):
        page.insert_text((xs[column] + 4, 160), text, fontsize=9)
    for column, text in enumerate(data):
        page.insert_text((xs[column] + 4, 190), text, fontsize=9)

    payload = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return payload


def _gate() -> ConformalExtractionGate:
    calibration = ConformalCalibration((0.01,) * 30, alpha=0.05)
    return ConformalExtractionGate(calibration, min_independent_families=2)


def test_dual_native_parsers_preserve_artifact_identity_and_table_values():
    pdf = _regression_pdf()
    snapshots = parse_pdf_dual(pdf, artifact_id="paper")
    assert {snapshot.parser_family for snapshot in snapshots} == {"mupdf_native", "pdfminer_native"}
    assert all(snapshot.artifact_sha256 == sha256(pdf).hexdigest() for snapshot in snapshots)
    assert all(snapshot.tables for snapshot in snapshots)
    assert all(any("Treatment" in table.text for table in snapshot.tables) for snapshot in snapshots)

    bundle = extract_regression_table(snapshots, variable_label="Treatment")
    assert len(bundle.field_candidates["beta"]) == 2
    assert {candidate.normalized_value for candidate in bundle.field_candidates["beta"]} == {"0.180"}
    assert {candidate.normalized_value for candidate in bundle.field_candidates["p_value"]} == {"0.003"}
    assert {candidate.normalized_value for candidate in bundle.semantic_candidates["inference_distribution"]} == {
        "normal"
    }
    assert all(candidate.source.page == 1 for candidate in bundle.field_candidates["beta"])
    assert all(candidate.source.bbox is not None for candidate in bundle.field_candidates["beta"])


def test_individual_parser_snapshots_have_stable_hashes():
    pdf = _regression_pdf()
    left = PyMuPDFNativeParser().parse_bytes(pdf)
    right = PDFPlumberNativeParser().parse_bytes(pdf)
    assert left.sha256() == PyMuPDFNativeParser().parse_bytes(pdf).sha256()
    assert right.sha256() == PDFPlumberNativeParser().parse_bytes(pdf).sha256()
    assert left.sha256() != right.sha256()


def test_valid_pdf_regression_is_detector_ready_but_not_production_authorized():
    pdf = _regression_pdf()
    ledger, spec = prepare_regression_pdf_audit(
        pdf,
        _gate(),
        variable_label="Treatment",
        calibration_sha256=calibration_manifest_sha256(b"synthetic-calibration-v1"),
    )
    report, envelope = ledger.promote("regression-1", spec, regression_result_builder)
    assert report.detector_ready
    assert not report.hard_audit_ready
    assert envelope is not None
    assert not envelope.production_authorized

    audit = AuditEngine().audit_verified([envelope])
    assert not any(finding.grade >= EvidenceGrade.INTERNAL_CONTRADICTION for finding in audit.findings)


def test_corrupted_p_value_reaches_e3_only_after_dual_parser_detector_promotion():
    pdf = _regression_pdf(p_value="0.400")
    ledger, spec = prepare_regression_pdf_audit(
        pdf,
        _gate(),
        variable_label="Treatment",
        calibration_sha256=calibration_manifest_sha256(b"synthetic-calibration-v1"),
    )
    report, envelope = ledger.promote("regression-1", spec, regression_result_builder)
    assert report.detector_ready
    assert not report.hard_audit_ready
    assert envelope is not None

    audit = AuditEngine().audit_verified([envelope])
    p_findings = [finding for finding in audit.findings if "p-value" in finding.explanation]
    assert len(p_findings) == 1
    assert p_findings[0].grade is EvidenceGrade.INTERNAL_CONTRADICTION
    provenance = p_findings[0].evidence["ingestion_provenance"]
    assert provenance["artifact_sha256"] == sha256(pdf).hexdigest()
    assert len(provenance["extraction_evidence_sha256"]) == 64
    assert provenance["production_hard_finding_authorized"] is False


def test_missing_second_parser_cannot_promote_to_detector():
    pdf = _regression_pdf()
    snapshot = PyMuPDFNativeParser().parse_bytes(pdf)
    bundle = extract_regression_table((snapshot,), variable_label="Treatment")
    from veritas.pdf_regression import bundle_to_ledger, regression_promotion_spec

    ledger = bundle_to_ledger(
        bundle,
        _gate(),
        calibration_sha256=calibration_manifest_sha256(b"synthetic-calibration-v1"),
        object_id="regression-1",
    )
    report, envelope = ledger.promote("regression-1", regression_promotion_spec(), regression_result_builder)
    assert not report.detector_ready
    assert not report.hard_audit_ready
    assert envelope is None
