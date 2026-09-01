from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .models import ReportedNumber, SourceLocation
from .reproduction import (
    ReproducedCell,
    ReproductionAuthority,
    ReproductionTarget,
    build_reproduction_report,
    compare_reproduced_cells,
    target_commitment_sha256,
)
from .types import ComparisonOperator, Materiality


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_private_reproduction_target(path: str | Path) -> ReproductionTarget:
    """Load a post-run target secret that must never enter an agent workspace."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    reported = data["reported"]
    source_data = dict(data.get("source", {}))
    if source_data.get("bbox") is not None:
        source_data["bbox"] = tuple(source_data["bbox"])
    return ReproductionTarget(
        target_id=str(data["target_id"]),
        claim_id=str(data["claim_id"]),
        metric=str(data["metric"]),
        reported=ReportedNumber(
            value=float(reported["value"]),
            decimals=(None if reported.get("decimals") is None else int(reported["decimals"])),
            operator=ComparisonOperator(reported.get("operator", "=")),
        ),
        source=SourceLocation(**source_data),
        materiality=Materiality(int(data.get("materiality", int(Materiality.SECONDARY_RESULT)))),
    )


def _require_equal(label: str, observed: object, expected: object) -> None:
    if observed != expected:
        raise ValueError(f"{label} does not match the locked reproduction packet")


def _validate_execution_evidence(
    packet: Mapping[str, Any],
    execution: Mapping[str, Any],
    output_path: Path,
) -> str:
    author_track = packet["execution_tracks"]["author_package"]
    frozen = author_track["frozen_rerun"]
    package = packet["replication_package"]

    _require_equal("execution case id", execution.get("case_id"), packet["case_id"])
    _require_equal("execution track", execution.get("track"), "author_package_frozen_environment_rerun")
    _require_equal("external git commit", execution.get("external_git_commit_sha"), package["git_commit_sha"])
    _require_equal("source manifest", execution.get("source_manifest_sha256"), frozen["source_manifest_sha256"])
    _require_equal(
        "environment freeze",
        execution.get("environment_freeze_sha256"),
        frozen["environment_freeze_sha256"],
    )
    _require_equal(
        "environment lock",
        execution.get("environment_lock_sha256"),
        author_track["environment_lock_sha256"],
    )
    _require_equal("base image", execution.get("base_image"), author_track["base_image"])

    if execution.get("exit_code") != 0:
        raise ValueError("frozen execution did not exit successfully")
    for field in ("network_disabled", "source_mount_read_only", "runtime_precommitted"):
        if execution.get(field) is not True:
            raise ValueError(f"frozen execution did not attest required property: {field}")
    for field in ("credentials_mounted", "veritas_repository_mounted"):
        if execution.get(field) is not False:
            raise ValueError(f"frozen execution unexpectedly exposed privileged context: {field}")

    output_sha256 = _sha256_file(output_path)
    _require_equal("output artifact", execution.get("output_artifact_sha256"), output_sha256)
    _require_equal("packet output artifact", frozen["output_artifact_sha256"], output_sha256)
    return output_sha256


def _extract_bound_csv_value(output_path: Path, binding: Mapping[str, Any]) -> float:
    if binding.get("format") != "csv":
        raise ValueError("only csv reproduced-value bindings are currently supported")
    row_match = binding.get("row_match")
    value_column = binding.get("value_column")
    if not isinstance(row_match, dict) or not row_match:
        raise ValueError("csv reproduced-value binding requires a non-empty row_match")
    if not isinstance(value_column, str) or not value_column:
        raise ValueError("csv reproduced-value binding requires value_column")

    with output_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    matches = [
        row
        for row in rows
        if all(row.get(str(key)) == str(expected) for key, expected in row_match.items())
    ]
    if len(matches) != 1:
        raise ValueError(f"reproduced-value binding matched {len(matches)} rows; expected exactly one")
    try:
        value = float(matches[0][value_column])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("bound reproduced value is missing or non-numeric") from exc
    if not math.isfinite(value):
        raise ValueError("bound reproduced value must be finite")
    return value


def build_answer_free_reproduction_certificate(
    *,
    packet: Mapping[str, Any],
    execution: Mapping[str, Any],
    private_target: ReproductionTarget,
    output_path: str | Path,
) -> dict[str, Any]:
    """Compare a frozen output with a post-run secret without persisting numeric answers."""

    target_contract = packet["target_contract"]
    output = Path(output_path)
    output_sha256 = _validate_execution_evidence(packet, execution, output)

    _require_equal("target id", private_target.target_id, target_contract["target_id"])
    _require_equal("claim id", private_target.claim_id, target_contract["claim_id"])
    _require_equal("target metric", private_target.metric, target_contract["metric"])
    observed_commitment = target_commitment_sha256((private_target,))
    _require_equal(
        "target commitment",
        observed_commitment,
        target_contract["target_commitment_sha256"],
    )
    _require_equal("execution target id", execution.get("target_id"), private_target.target_id)

    binding = target_contract["reproduced_value_binding"]
    reproduced_value = _extract_bound_csv_value(output, binding)
    if "reproduced_value" in execution:
        attested_value = float(execution["reproduced_value"])
        if not math.isclose(attested_value, reproduced_value, rel_tol=0.0, abs_tol=0.0):
            raise ValueError("execution attestation value does not match the bound output artifact")

    comparisons = compare_reproduced_cells(
        (private_target,),
        (ReproducedCell(private_target.target_id, reproduced_value, output_sha256),),
    )
    report = build_reproduction_report(
        comparisons,
        authority=ReproductionAuthority.AUTHOR_PACKAGE_RERUN,
        method_fidelity_verified=False,
        artifact_identity_verified=True,
        execution_attested=True,
    )
    comparison = report.comparisons[0]

    return {
        "schema_version": 1,
        "case_id": packet["case_id"],
        "track": "author_package_frozen_environment_rerun",
        "status": "descriptive_comparison_pending_independent_review",
        "target": {
            "target_id": private_target.target_id,
            "target_commitment_sha256": observed_commitment,
            "reported_numeric_value_stored_in_certificate": False,
            "post_run_unseal_checked_by_veritas": True,
        },
        "execution": {
            "external_git_commit_sha": execution["external_git_commit_sha"],
            "source_manifest_sha256": execution["source_manifest_sha256"],
            "base_image": execution["base_image"],
            "environment_lock_sha256": execution["environment_lock_sha256"],
            "environment_freeze_sha256": execution["environment_freeze_sha256"],
            "output_artifact_sha256": output_sha256,
            "exit_code": 0,
            "network_disabled": True,
            "source_mount_read_only": True,
            "veritas_repository_mounted": False,
            "credentials_mounted": False,
            "runtime_precommitted": True,
        },
        "comparison": {
            "decision": report.decision.value.upper(),
            "status": comparison.status.value.upper(),
            "metric": comparison.metric,
            "comparator": "veritas_rounding_interval_numeric_equality",
            "target_commitment_validated": True,
            "output_artifact_bound": comparison.output_artifact_sha256 == output_sha256,
            "numeric_values_persisted_in_certificate": False,
        },
        "review": {
            "target_reviewer_a_complete": bool(target_contract.get("reviewer_a_complete")),
            "target_reviewer_b_complete": bool(target_contract.get("reviewer_b_complete")),
            "target_adjudication_complete": bool(target_contract.get("adjudication_complete")),
            "method_fidelity_independent_complete": False,
        },
        "authority": {
            "production_authorized": False,
            "e4_authorized": False,
            "max_evidence_grade": report.max_evidence_grade.name,
            "reasons": list(report.reasons),
        },
    }


def build_answer_free_certificate_from_files(
    *,
    packet_path: str | Path,
    execution_path: str | Path,
    private_target_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
    execution = json.loads(Path(execution_path).read_text(encoding="utf-8"))
    target = load_private_reproduction_target(private_target_path)
    return build_answer_free_reproduction_certificate(
        packet=packet,
        execution=execution,
        private_target=target,
        output_path=output_path,
    )
