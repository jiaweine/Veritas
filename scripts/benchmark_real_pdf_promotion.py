from __future__ import annotations

import json
from dataclasses import replace

from smoke_real_pdf import CASES, SEED_MANIFEST, SEED_MANIFEST_SHA256, _download
from veritas.audit import AuditEngine
from veritas.extraction import ConformalCalibration, ConformalExtractionGate
from veritas.ingestion import CalibrationScope
from veritas.pdf_native import parse_pdf_dual
from veritas.pdf_regression import (
    RegressionLocator,
    bundle_to_ledger,
    calibration_manifest_sha256,
    extract_regression_table,
    regression_promotion_spec,
    regression_result_builder,
)


def _gate(score: float) -> tuple[ConformalExtractionGate, str]:
    payload = json.dumps(
        {
            "scope": "real-pdf-promotion-benchmark-only",
            "score": score,
            "note": "Synthetic threshold probe; not production calibration.",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    calibration = ConformalCalibration(nonconformity_scores=(score,) * 40, alpha=0.05)
    return ConformalExtractionGate(calibration), calibration_manifest_sha256(payload)


def _promotion_expectations() -> dict[str, dict[str, object]]:
    payload = json.loads(SEED_MANIFEST.read_text(encoding="utf-8"))
    expectations: dict[str, dict[str, object]] = {}
    for case in payload["cases"]:
        expectation = case.get("promotion_expectation")
        if not isinstance(expectation, dict) or "detector_ready_under_geometry_probe" not in expectation:
            raise RuntimeError(f"seed case lacks explicit promotion expectation: {case['case_id']}")
        expectations[str(case["case_id"])] = expectation
    return expectations


PROMOTION_EXPECTATIONS = _promotion_expectations()


def _exact_gold(bundle: object, expected: dict[str, object]) -> bool:
    fields = getattr(bundle, "field_candidates")
    for key, gold in expected.items():
        candidates = fields[key]
        if len(candidates) != 2:
            return False
        if any(candidate.normalized_value != gold for candidate in candidates):
            return False
    return True


def _candidate_modes(bundle: object) -> tuple[str, ...]:
    fields = getattr(bundle, "field_candidates")
    modes: set[str] = set()
    for candidates in fields.values():
        for candidate in candidates:
            parser_id = candidate.parser_id
            modes.add(parser_id.rsplit(":", 1)[-1] if ":" in parser_id else parser_id)
    return tuple(sorted(modes))


def _evaluate_policy(
    bundle: object,
    *,
    gate_score: float,
    object_id: str,
) -> dict[str, object]:
    gate, calibration_sha = _gate(gate_score)
    ledger = bundle_to_ledger(
        bundle,
        gate,
        calibration_sha256=calibration_sha,
        object_id=object_id,
    )
    ledger.protocol = replace(ledger.protocol, calibration_scope=CalibrationScope.BENCHMARK)
    spec = regression_promotion_spec()
    report, envelope = ledger.promote(object_id, spec, regression_result_builder)
    result: dict[str, object] = {
        "decision": report.decision.value,
        "detector_ready": report.detector_ready,
        "hard_audit_ready": report.hard_audit_ready,
        "calibration_scope": report.calibration_scope.value,
        "reasons": report.reasons,
        "protocol_sha256": report.protocol_sha256,
        "promotion_spec_sha256": report.promotion_spec_sha256,
        "evidence_sha256": report.evidence_sha256,
    }
    if envelope is None:
        result["checks"] = []
        result["e3_findings"] = 0
        result["production_authorized"] = False
        return result

    result["production_authorized"] = envelope.production_authorized
    summary = AuditEngine().audit_verified((envelope,))
    result["checks"] = [
        {
            "detector_id": check.detector_id,
            "check_id": check.check_id,
            "status": check.status.value,
        }
        for check in summary.checks
    ]
    result["e3_findings"] = len(summary.findings)
    result["verification_coverage"] = summary.verification_coverage
    if summary.findings:
        result["finding_production_authority"] = [
            finding.evidence["ingestion_provenance"]["production_hard_finding_authorized"]
            for finding in summary.findings
        ]
    return result


def main() -> None:
    case_results: list[dict[str, object]] = []
    extraction_ok_count = 0
    conservative_detector_promoted = 0
    geometry_detector_promoted = 0
    promotion_eligible_cases = 0
    promotion_eligible_promoted = 0
    production_authorized = 0
    geometry_e3_cases: list[str] = []
    expected_abstention_case_ids: list[str] = []
    failures: list[str] = []

    for case in CASES:
        case_id = str(case["case_id"])
        expectation = PROMOTION_EXPECTATIONS[case_id]
        expected_geometry_ready = bool(expectation["detector_ready_under_geometry_probe"])
        if not expected_geometry_ready:
            expected_abstention_case_ids.append(case_id)

        pdf = _download(str(case["pdf_url"]))
        snapshots = parse_pdf_dual(pdf, artifact_id=f"promotion-{case_id}")
        bundle = extract_regression_table(
            snapshots,
            variable_label=str(case["variable"]),
            locator=RegressionLocator(
                table_label=str(case["table_label"]),
                expected_page=int(case["expected_page"]),
            ),
        )
        expected = {str(key): str(value) for key, value in dict(case["expected"]).items()}
        extraction_ok = _exact_gold(bundle, expected) and not bundle.ambiguities
        extraction_ok_count += int(extraction_ok)
        if not extraction_ok:
            failures.append(f"{case_id}:extraction")

        conservative = _evaluate_policy(
            bundle,
            gate_score=0.01,
            object_id=f"{case_id}-native-threshold",
        )
        geometry = _evaluate_policy(
            bundle,
            gate_score=0.02,
            object_id=f"{case_id}-geometry-threshold",
        )
        conservative_detector_promoted += int(bool(conservative["detector_ready"]))
        geometry_detector_promoted += int(bool(geometry["detector_ready"]))
        if expected_geometry_ready:
            promotion_eligible_cases += 1
            promotion_eligible_promoted += int(bool(geometry["detector_ready"]))
        if bool(geometry["detector_ready"]) != expected_geometry_ready:
            failures.append(f"{case_id}:geometry-promotion-expectation")
        production_authorized += int(bool(geometry["hard_audit_ready"]))
        if int(geometry["e3_findings"]) > 0:
            geometry_e3_cases.append(case_id)
        if geometry["calibration_scope"] != CalibrationScope.BENCHMARK.value:
            failures.append(f"{case_id}:benchmark-scope")
        if bool(geometry["production_authorized"]) or bool(geometry["hard_audit_ready"]):
            failures.append(f"{case_id}:benchmark-gained-production-authority")

        case_results.append(
            {
                "case_id": case_id,
                "doi": case["doi"],
                "exact_extraction_gold_match": extraction_ok,
                "candidate_modes": _candidate_modes(bundle),
                "artifact_sha256": bundle.artifact_sha256,
                "source_page": bundle.source.page,
                "source_table": bundle.source.table,
                "promotion_expectation": expectation,
                "conservative_native_threshold": conservative,
                "experimental_geometry_threshold": geometry,
            }
        )

    total = len(CASES)
    # The geometry threshold is deliberately benchmark-only. It may exercise the detector pipeline
    # only when the publication itself supplies the semantic prerequisites. Exact extraction is a
    # separate success criterion and must not be converted into guessed method semantics.
    if promotion_eligible_promoted != promotion_eligible_cases:
        failures.append("promotion-eligible-geometry-coverage")
    if production_authorized != 0:
        failures.append("benchmark-production-authority-must-be-zero")

    report = {
        "scope": "real_open_access_selective_promotion_benchmark_not_production_certification",
        "seed_manifest_sha256": SEED_MANIFEST_SHA256,
        "cases": total,
        "exact_extraction_coverage": extraction_ok_count / total if total else 0.0,
        "conservative_native_threshold_detector_promotion_coverage": (
            conservative_detector_promoted / total if total else 0.0
        ),
        "experimental_geometry_threshold_detector_promotion_coverage": (
            geometry_detector_promoted / total if total else 0.0
        ),
        "promotion_eligible_cases": promotion_eligible_cases,
        "promotion_eligible_detector_coverage": (
            promotion_eligible_promoted / promotion_eligible_cases if promotion_eligible_cases else 0.0
        ),
        "expected_abstention_case_ids": expected_abstention_case_ids,
        "benchmark_production_hard_authority_coverage": production_authorized / total if total else 0.0,
        "experimental_promoted_e3_case_ids": geometry_e3_cases,
        "failed_checks": failures,
        "results": case_results,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if failures:
        raise SystemExit("real-PDF selective-promotion benchmark failed")


if __name__ == "__main__":
    main()
