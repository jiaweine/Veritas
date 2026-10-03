from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from veritas.auditbench import (
    AuditBenchExpectation,
    AuditBenchObservation,
    evaluate_auditbench,
)
from veritas.detectors.correlation import CorrelationPSDDetector
from veritas.detectors.designs import DIDDesignDetector, WeakIVDesignDetector
from veritas.detectors.rdd import RDDDesignDetector
from veritas.detectors.regression import RegressionConsistencyDetector
from veritas.detectors.sample import SampleAccountingDetector
from veritas.detectors.standardized_regression import StandardizedRegressionReconstructionDetector
from veritas.models import (
    CorrelationMatrix,
    DIDDesign,
    IVDesign,
    RDDDesign,
    RegressionResult,
    ReportedNumber,
    SamplePartition,
    StandardizedRegressionReconstruction,
)
from veritas.types import CheckStatus, ComparisonOperator, EvidenceGrade, Materiality

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = ROOT / "benchmark/auditbench/v1_protocol.json"
DEFAULT_CASES = ROOT / "benchmark/auditbench/v1_cases.json"
DEFAULT_LOCK = ROOT / "benchmark/auditbench/v1_lock.json"
DEFAULT_OUTPUT = ROOT / "benchmark-result-envelopes/auditbench-v1.json"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_locked_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return raw, payload


def _reported(payload: dict[str, Any] | None) -> ReportedNumber | None:
    if payload is None:
        return None
    return ReportedNumber(
        value=float(payload["value"]),
        decimals=int(payload["decimals"]) if payload.get("decimals") is not None else None,
        operator=ComparisonOperator(payload.get("operator", "=")),
    )


def _required_reported(fixture: dict[str, Any], key: str) -> ReportedNumber:
    value = _reported(fixture.get(key))
    if value is None:
        raise ValueError(f"fixture requires {key!r}")
    return value


def _correlation_matrix(
    fixture: dict[str, Any],
    *,
    object_id: str,
    materiality: Materiality,
) -> CorrelationMatrix:
    labels = fixture.get("labels")
    cells = fixture.get("cells")
    if not isinstance(labels, list) or not isinstance(cells, list):
        raise TypeError(f"case {object_id!r} correlation matrix requires labels/cells arrays")
    return CorrelationMatrix(
        object_id=object_id,
        labels=tuple(str(value) for value in labels),
        cells=tuple(tuple(_reported(value) for value in row) for row in cells),
        materiality=materiality,
    )


def _fixture(case: dict[str, Any]) -> object:
    fixture = case["fixture"]
    materiality = Materiality[case["materiality"]]
    object_id = str(case["case_id"])
    fixture_type = fixture["type"]

    if fixture_type == "regression":
        return RegressionResult(
            object_id=object_id,
            beta=_required_reported(fixture, "beta"),
            se=_reported(fixture.get("se")),
            t_stat=_reported(fixture.get("t_stat")),
            p_value=_reported(fixture.get("p_value")),
            ci_lower=_reported(fixture.get("ci_lower")),
            ci_upper=_reported(fixture.get("ci_upper")),
            ci_level=float(fixture.get("ci_level", 0.95)),
            degrees_of_freedom=(
                float(fixture["degrees_of_freedom"])
                if fixture.get("degrees_of_freedom") is not None
                else None
            ),
            inference_distribution=str(fixture.get("inference_distribution", "unknown")),
            p_value_adjusted=bool(fixture.get("p_value_adjusted", False)),
            materiality=materiality,
        )

    if fixture_type == "sample_partition":
        groups = fixture.get("groups") or {}
        if not isinstance(groups, dict):
            raise TypeError(f"case {object_id!r} groups must be an object")
        return SamplePartition(
            object_id=object_id,
            total_n=int(fixture["total_n"]) if fixture.get("total_n") is not None else None,
            groups={str(key): int(value) for key, value in groups.items()},
            exhaustive=fixture.get("exhaustive"),
            non_overlapping=bool(fixture.get("non_overlapping", True)),
            explanation_present=fixture.get("explanation_present"),
            materiality=materiality,
        )

    if fixture_type == "correlation_matrix":
        return _correlation_matrix(fixture, object_id=object_id, materiality=materiality)

    if fixture_type == "standardized_regression":
        matrix = _correlation_matrix(
            fixture,
            object_id=f"{object_id}:correlations",
            materiality=materiality,
        )
        beta_payloads = fixture.get("standardized_betas")
        predictors = fixture.get("predictors")
        if not isinstance(beta_payloads, list) or not isinstance(predictors, list):
            raise TypeError(
                f"case {object_id!r} standardized regression requires predictors/betas arrays"
            )
        betas = tuple(_reported(value) for value in beta_payloads)
        if any(value is None for value in betas):
            raise ValueError(f"case {object_id!r} standardized betas may not be null")
        return StandardizedRegressionReconstruction(
            object_id=object_id,
            correlation_matrix=matrix,
            outcome=str(fixture["outcome"]),
            predictors=tuple(str(value) for value in predictors),
            standardized_betas=tuple(value for value in betas if value is not None),
            ols_identity_verified=bool(fixture.get("ols_identity_verified", False)),
            same_sample_verified=bool(fixture.get("same_sample_verified", False)),
            complete_predictor_set_verified=bool(
                fixture.get("complete_predictor_set_verified", False)
            ),
            materiality=materiality,
        )

    if fixture_type == "did_design":
        event_time_window = fixture.get("event_time_window")
        if event_time_window is not None:
            if not isinstance(event_time_window, list) or len(event_time_window) != 2:
                raise TypeError(f"case {object_id!r} event_time_window must contain two values")
            event_time_window = (int(event_time_window[0]), int(event_time_window[1]))
        return DIDDesign(
            object_id=object_id,
            periods=int(fixture["periods"]) if fixture.get("periods") is not None else None,
            staggered_adoption=fixture.get("staggered_adoption"),
            treatment_type=str(fixture.get("treatment_type", "binary")),
            estimator=fixture.get("estimator"),
            event_study=fixture.get("event_study"),
            heterogeneity_robust_estimator_reported=fixture.get(
                "heterogeneity_robust_estimator_reported"
            ),
            treatment_timing=fixture.get("treatment_timing"),
            comparison_group=fixture.get("comparison_group"),
            event_time_window=event_time_window,
            fixed_effects=tuple(str(value) for value in fixture.get("fixed_effects") or []),
            clustering=tuple(str(value) for value in fixture.get("clustering") or []),
            pretrend_test=fixture.get("pretrend_test"),
            parallel_trends_claimed=fixture.get("parallel_trends_claimed"),
            materiality=materiality,
        )

    if fixture_type == "iv_design":
        return IVDesign(
            object_id=object_id,
            single_instrument=fixture.get("single_instrument"),
            single_endogenous_regressor=fixture.get("single_endogenous_regressor"),
            just_identified=fixture.get("just_identified"),
            instrument_count=(
                int(fixture["instrument_count"])
                if fixture.get("instrument_count") is not None
                else None
            ),
            endogenous_regressor_count=(
                int(fixture["endogenous_regressor_count"])
                if fixture.get("endogenous_regressor_count") is not None
                else None
            ),
            first_stage_reported=fixture.get("first_stage_reported"),
            reduced_form_reported=fixture.get("reduced_form_reported"),
            two_stage_least_squares_reported=fixture.get("two_stage_least_squares_reported"),
            first_stage_f=_reported(fixture.get("first_stage_f")),
            uses_f_gt_10_rule_as_validity_claim=bool(
                fixture.get("uses_f_gt_10_rule_as_validity_claim", False)
            ),
            weak_robust_methods=tuple(
                str(value) for value in fixture.get("weak_robust_methods") or []
            ),
            materiality=materiality,
        )

    if fixture_type == "rdd_design":
        return RDDDesign(
            object_id=object_id,
            framework=str(fixture.get("framework", "unknown")),
            design_type=str(fixture.get("design_type", "sharp")),
            estimator=fixture.get("estimator"),
            running_variable=fixture.get("running_variable"),
            cutoff=_reported(fixture.get("cutoff")),
            bandwidth=_reported(fixture.get("bandwidth")),
            bandwidth_selection=fixture.get("bandwidth_selection"),
            kernel=fixture.get("kernel"),
            inference_description=fixture.get("inference_description"),
            global_polynomial_order=(
                int(fixture["global_polynomial_order"])
                if fixture.get("global_polynomial_order") is not None
                else None
            ),
            robust_bias_corrected_inference=fixture.get("robust_bias_corrected_inference"),
            alternative_modern_inference_reported=fixture.get(
                "alternative_modern_inference_reported"
            ),
            randomization_inference_reported=fixture.get("randomization_inference_reported"),
            continuity_check_claimed=fixture.get("continuity_check_claimed"),
            continuity_check_reported=fixture.get("continuity_check_reported"),
            manipulation_check_claimed=fixture.get("manipulation_check_claimed"),
            density_test_reported=fixture.get("density_test_reported"),
            materiality=materiality,
        )

    raise ValueError(f"unsupported AuditBench fixture type: {fixture_type!r}")


def _expectation(case: dict[str, Any]) -> AuditBenchExpectation:
    return AuditBenchExpectation(
        case_id=str(case["case_id"]),
        paper_id=str(case["paper_id"]),
        detector_id=str(case["detector_id"]),
        check_id=str(case["check_id"]),
        corruption_family=str(case["corruption_family"]),
        affected_claim_ids=tuple(str(value) for value in case.get("affected_claim_ids") or []),
        materiality=Materiality[case["materiality"]],
        discipline=str(case["discipline"]),
        reporting_style=str(case["reporting_style"]),
        expected_status=CheckStatus(case["expected_status"]),
        maximum_allowed_grade=EvidenceGrade[case["maximum_allowed_grade"]],
        extraction_error_case=bool(case.get("extraction_error_case", False)),
        benign_exception=bool(case.get("benign_exception", False)),
    )


def _detectors() -> dict[str, object]:
    return {
        "correlation_psd_sdp": CorrelationPSDDetector(),
        "did_design_frontier": DIDDesignDetector(),
        "rdd_design_frontier": RDDDesignDetector(),
        "regression_consistency": RegressionConsistencyDetector(),
        "sample_accounting": SampleAccountingDetector(),
        "standardized_regression_mccormick_sdp": StandardizedRegressionReconstructionDetector(),
        "weak_iv_frontier": WeakIVDesignDetector(),
    }


def _observation(case: dict[str, Any]) -> AuditBenchObservation:
    detector_id = str(case["detector_id"])
    try:
        detector = _detectors()[detector_id]
    except KeyError as exc:
        raise ValueError(f"unregistered AuditBench detector: {detector_id!r}") from exc
    checks = detector.run(_fixture(case))
    matching = [item for item in checks if item.check_id == case["check_id"]]
    if len(matching) != 1:
        raise ValueError(
            f"case {case['case_id']!r} expected exactly one {case['check_id']!r} check; "
            f"found {len(matching)}"
        )
    check = matching[0]
    return AuditBenchObservation(
        case_id=str(case["case_id"]),
        detector_id=check.detector_id,
        check_id=check.check_id,
        status=check.status,
        grade=check.finding.grade if check.finding is not None else None,
    )


def run(protocol_path: Path, cases_path: Path, lock_path: Path) -> dict[str, Any]:
    protocol_raw, protocol = _read_locked_json(protocol_path)
    cases_raw, corpus = _read_locked_json(cases_path)
    _, lock = _read_locked_json(lock_path)

    protocol_sha = _sha256(protocol_raw)
    cases_sha = _sha256(cases_raw)
    if protocol_sha != lock.get("protocol_sha256"):
        raise ValueError("AuditBench protocol bytes do not match the locked SHA-256")
    if cases_sha != lock.get("cases_sha256"):
        raise ValueError("AuditBench case bytes do not match the locked SHA-256")
    benchmark_id = str(protocol.get("benchmark_id"))
    if benchmark_id != corpus.get("benchmark_id") or benchmark_id != lock.get("benchmark_id"):
        raise ValueError("AuditBench benchmark identity is inconsistent across protocol/cases/lock")
    if protocol.get("split") != "test":
        raise ValueError("AuditBench CI corpus must be a locked test split")
    governance = protocol.get("governance") or {}
    if governance.get("synthetic_ci_results_are_not_production_certification") is not True:
        raise ValueError("AuditBench synthetic CI corpus must explicitly deny production certification")
    if governance.get("production_e3_requires_external_benchmark_evidence") is not True:
        raise ValueError("AuditBench must preserve the external evidence gate for production E3+")

    raw_cases = corpus.get("cases")
    if not isinstance(raw_cases, list):
        raise TypeError("AuditBench locked case corpus cases must be an array")
    if not raw_cases:
        raise ValueError("AuditBench locked case corpus must contain at least one case")
    expectations = tuple(_expectation(case) for case in raw_cases)
    observations = tuple(_observation(case) for case in raw_cases)
    policy = protocol["policy"]
    report = evaluate_auditbench(
        expectations,
        observations,
        min_alert_precision=float(policy["min_alert_precision"]),
        min_alert_recall=float(policy["min_alert_recall"]),
        max_false_hard_alert_rate_per_clean_paper=float(
            policy["max_false_hard_alert_rate_per_clean_paper"]
        ),
        max_grade_violation_rate=float(policy["max_grade_violation_rate"]),
    )
    return {
        "schema_version": 1,
        "benchmark_id": benchmark_id,
        "status": "pass" if report.passed else "fail",
        "protocol_sha256": protocol_sha,
        "cases_sha256": cases_sha,
        "production_certificate": False,
        "external_real_paper_milestone_issue": governance.get(
            "external_real_paper_milestone_issue"
        ),
        "reasons": list(report.reasons),
        "overall": asdict(report.overall),
        "by_detector": {key: asdict(value) for key, value in report.by_detector.items()},
        "by_materiality": {key: asdict(value) for key, value in report.by_materiality.items()},
        "by_discipline": {key: asdict(value) for key, value in report.by_discipline.items()},
        "by_reporting_style": {
            key: asdict(value) for key, value in report.by_reporting_style.items()
        },
        "observations": [
            {
                "case_id": item.case_id,
                "detector_id": item.detector_id,
                "check_id": item.check_id,
                "status": item.status.value,
                "grade": item.grade.name if item.grade is not None else None,
            }
            for item in observations
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the locked synthetic AuditBench v1 CI gate.")
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    payload = run(args.protocol, args.cases, args.lock)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True, indent=2))
    if payload["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
