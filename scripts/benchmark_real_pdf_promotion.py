from __future__ import annotations

import json

from smoke_real_pdf import CASES, _download
from veritas.audit import AuditEngine
from veritas.extraction import ConformalCalibration, ConformalExtractionGate
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
    spec = regression_promotion_spec()
    report, envelope = ledger.promote(object_id, spec, regression_result_builder)
    result: dict[str, object] = {
        "decision": report.decision.value,
        "hard_audit_ready": report.hard_audit_ready,
        "reasons": report.reasons,
        "protocol_sha256": report.protocol_sha256,
        "promotion_spec_sha256": report.promotion_spec_sha256,
        "evidence_sha256": report.evidence_sha256,
    }
    if envelope is None:
        result["checks"] = []
        result["e3_findings"] = 0
        return result

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
    return result


def main() -> None:
    case_results: list[dict[str, object]] = []
    extraction_ok_count = 0
    conservative_promoted = 0
    geometry_promoted = 0
    geometry_e3_cases: list[str] = []
    failures: list[str] = []

    for case in CASES:
        case_id = str(case["case_id"])
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
        conservative_promoted += int(bool(conservative["hard_audit_ready"]))
        geometry_promoted += int(bool(geometry["hard_audit_ready"]))
        if int(geometry["e3_findings"]) > 0:
            geometry_e3_cases.append(case_id)

        case_results.append(
            {
                "case_id": case_id,
                "doi": case["doi"],
                "exact_extraction_gold_match": extraction_ok,
                "candidate_modes": _candidate_modes(bundle),
                "artifact_sha256": bundle.artifact_sha256,
                "source_page": bundle.source.page,
                "source_table": bundle.source.table,
                "conservative_native_threshold": conservative,
                "experimental_geometry_threshold": geometry,
            }
        )

    total = len(CASES)
    # The geometry threshold is deliberately a benchmark-only synthetic probe. Because the
    # extraction gold is already manually fixed for these cases, failure to promote here means
    # the promotion plumbing—not the real paper's correctness—has regressed.
    if geometry_promoted != extraction_ok_count:
        failures.append("experimental-geometry-promotion-coverage")

    report = {
        "scope": "real_open_access_selective_promotion_benchmark_not_production_certification",
        "cases": total,
        "exact_extraction_coverage": extraction_ok_count / total if total else 0.0,
        "conservative_native_threshold_promotion_coverage": conservative_promoted / total if total else 0.0,
        "experimental_geometry_threshold_promotion_coverage": geometry_promoted / total if total else 0.0,
        "experimental_promoted_e3_case_ids": geometry_e3_cases,
        "failed_checks": failures,
        "results": case_results,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if failures:
        raise SystemExit("real-PDF selective-promotion benchmark failed")


if __name__ == "__main__":
    main()
