from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from veritas.auditbench import AuditBenchExpectation, AuditBenchObservation, evaluate_auditbench
from veritas.detectors.algebra import LogitOddsRatioDetector, MediationProductDetector
from veritas.detectors.discrete import DiscreteSummaryFeasibilityDetector
from veritas.detectors.sem import SEMFitArithmeticDetector
from veritas.models import DiscreteSummary, LogitResult, MediationResult, ReportedNumber
from veritas.sem import SEMFitSummary
from veritas.types import CheckStatus, ComparisonOperator, EvidenceGrade, Materiality

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = ROOT / "benchmark/auditbench/v1_protocol.json"
DEFAULT_CASES = ROOT / "benchmark/auditbench/v02_pack_cases.json"
DEFAULT_LOCK = ROOT / "benchmark/auditbench/v02_pack_lock.json"
DEFAULT_OUTPUT = ROOT / "auditbench-raw-reports/auditbench-v02-pack.json"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> tuple[bytes, dict[str, Any]]:
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


def _fixture(case: dict[str, Any]) -> object:
    fixture = case["fixture"]
    object_id = str(case["case_id"])
    materiality = Materiality[case["materiality"]]
    fixture_type = fixture["type"]

    if fixture_type == "discrete_summary":
        return DiscreteSummary(
            object_id=object_id,
            n=int(fixture["n"]),
            mean=_required_reported(fixture, "mean"),
            sd=_reported(fixture.get("sd")),
            sd_definition=str(fixture.get("sd_definition", "unknown")),
            support=tuple(float(value) for value in fixture["support"]),
            support_verified=bool(fixture.get("support_verified", False)),
            n_verified=bool(fixture.get("n_verified", False)),
            weighted=fixture.get("weighted"),
            materiality=materiality,
        )

    if fixture_type == "logit_result":
        return LogitResult(
            object_id=object_id,
            beta=_required_reported(fixture, "beta"),
            odds_ratio=_required_reported(fixture, "odds_ratio"),
            exp_beta_relation_verified=bool(fixture.get("exp_beta_relation_verified", False)),
            materiality=materiality,
        )

    if fixture_type == "mediation_result":
        return MediationResult(
            object_id=object_id,
            a_path=_required_reported(fixture, "a_path"),
            b_path=_required_reported(fixture, "b_path"),
            indirect_effect=_required_reported(fixture, "indirect_effect"),
            product_definition_verified=bool(fixture.get("product_definition_verified", False)),
            scale_consistent_verified=bool(fixture.get("scale_consistent_verified", False)),
            materiality=materiality,
        )

    if fixture_type == "sem_fit":
        return SEMFitSummary(
            object_id=object_id,
            chi_square=_required_reported(fixture, "chi_square"),
            degrees_of_freedom=int(fixture["degrees_of_freedom"]),
            reported_p_value=_reported(fixture.get("reported_p_value")),
            n_observations=(
                int(fixture["n_observations"])
                if fixture.get("n_observations") is not None
                else None
            ),
            reported_rmsea=_reported(fixture.get("reported_rmsea")),
            rmsea_sample_size_basis=str(fixture.get("rmsea_sample_size_basis", "unknown")),
            baseline_chi_square=_reported(fixture.get("baseline_chi_square")),
            baseline_degrees_of_freedom=(
                int(fixture["baseline_degrees_of_freedom"])
                if fixture.get("baseline_degrees_of_freedom") is not None
                else None
            ),
            reported_cfi=_reported(fixture.get("reported_cfi")),
            reported_tli=_reported(fixture.get("reported_tli")),
            log_likelihood=_reported(fixture.get("log_likelihood")),
            free_parameters=(
                int(fixture["free_parameters"])
                if fixture.get("free_parameters") is not None
                else None
            ),
            reported_aic=_reported(fixture.get("reported_aic")),
            reported_bic=_reported(fixture.get("reported_bic")),
            estimator_path=str(fixture.get("estimator_path", "unknown")),
            unscaled_fit_statistics_verified=bool(
                fixture.get("unscaled_fit_statistics_verified", False)
            ),
            baseline_model_verified=bool(fixture.get("baseline_model_verified", False)),
            information_criteria_definition=str(
                fixture.get("information_criteria_definition", "unknown")
            ),
            materiality=materiality,
        )

    raise ValueError(f"unsupported AuditBench v0.2 fixture type: {fixture_type!r}")


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
        "discrete_summary_feasibility": DiscreteSummaryFeasibilityDetector(),
        "logit_odds_ratio_consistency": LogitOddsRatioDetector(),
        "mediation_product_consistency": MediationProductDetector(),
        "sem_fit_arithmetic": SEMFitArithmeticDetector(),
    }


def _observation(case: dict[str, Any]) -> AuditBenchObservation:
    detector_id = str(case["detector_id"])
    try:
        detector = _detectors()[detector_id]
    except KeyError as exc:
        raise ValueError(f"unregistered AuditBench v0.2 detector: {detector_id!r}") from exc
    matches = [
        result
        for result in detector.run(_fixture(case))
        if result.check_id == case["check_id"]
    ]
    if len(matches) != 1:
        raise ValueError(
            f"case {case['case_id']!r} expected one {case['check_id']!r} check; "
            f"found {len(matches)}"
        )
    check = matches[0]
    return AuditBenchObservation(
        case_id=str(case["case_id"]),
        detector_id=check.detector_id,
        check_id=check.check_id,
        status=check.status,
        grade=check.finding.grade if check.finding is not None else None,
    )


def run(protocol_path: Path, cases_path: Path, lock_path: Path) -> dict[str, Any]:
    protocol_raw, protocol = _read_json(protocol_path)
    cases_raw, corpus = _read_json(cases_path)
    _, lock = _read_json(lock_path)

    protocol_sha = _sha256(protocol_raw)
    cases_sha = _sha256(cases_raw)
    if protocol_sha != lock.get("protocol_sha256"):
        raise ValueError("AuditBench protocol bytes do not match the v0.2 pack lock")
    if cases_sha != lock.get("cases_sha256"):
        raise ValueError("AuditBench v0.2 case bytes do not match the locked SHA-256")
    benchmark_id = str(protocol.get("benchmark_id"))
    if benchmark_id != corpus.get("benchmark_id") or benchmark_id != lock.get("benchmark_id"):
        raise ValueError("AuditBench v0.2 benchmark identity is inconsistent")
    if protocol.get("split") != "test":
        raise ValueError("AuditBench v0.2 pack must use the locked test protocol")
    governance = protocol.get("governance") or {}
    if governance.get("synthetic_ci_results_are_not_production_certification") is not True:
        raise ValueError("Synthetic v0.2 pack must explicitly deny production certification")
    if governance.get("production_e3_requires_external_benchmark_evidence") is not True:
        raise ValueError("Production E3 must remain gated on external benchmark evidence")

    raw_cases = corpus.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("AuditBench v0.2 pack must contain cases")
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
        "pack_id": "v02-paper-only-detectors",
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
    parser = argparse.ArgumentParser(description="Run the locked AuditBench v0.2 detector pack.")
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
