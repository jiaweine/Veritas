from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import ReportedNumber, SourceLocation
from .reproduction import (
    CellComparison,
    ReproducedCell,
    ReproductionAuthority,
    ReproductionTarget,
    build_reproduction_report,
    compare_reproduced_cells,
    target_commitment_sha256,
)
from .reproduction_ingest import _require_equal, _validate_execution_evidence
from .reproduction_ingest_contract import validate_target_set_ingest_contract
from .reproduction_json import finite_reproduction_float, load_strict_reproduction_json
from .types import ComparisonOperator, Materiality


def _target_from_mapping(data: Mapping[str, Any]) -> ReproductionTarget:
    reported = data["reported"]
    if not isinstance(reported, Mapping):
        raise TypeError("private target reported field must be an object")
    source_data = dict(data.get("source", {}))
    if source_data.get("bbox") is not None:
        source_data["bbox"] = tuple(source_data["bbox"])
    return ReproductionTarget(
        target_id=str(data["target_id"]),
        claim_id=str(data["claim_id"]),
        metric=str(data["metric"]),
        reported=ReportedNumber(
            value=finite_reproduction_float(
                reported["value"],
                label="private target reported value",
            ),
            decimals=(None if reported.get("decimals") is None else int(reported["decimals"])),
            operator=ComparisonOperator(reported.get("operator", "=")),
        ),
        source=SourceLocation(**source_data),
        materiality=Materiality(int(data.get("materiality", int(Materiality.SECONDARY_RESULT)))),
    )


def load_private_reproduction_target_set(path: str | Path) -> tuple[ReproductionTarget, ...]:
    """Load an ordered post-run target set without exposing numeric answers to the executor."""

    decoded = load_strict_reproduction_json(path)
    if not isinstance(decoded, dict) or set(decoded) != {"schema_version", "targets"}:
        raise ValueError("private target set must contain exactly schema_version and targets")
    if decoded["schema_version"] != 1:
        raise ValueError("unsupported private target-set schema_version")
    rows = decoded["targets"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("private target set requires at least one target")

    targets: list[ReproductionTarget] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("private target rows must be objects")
        targets.append(_target_from_mapping(row))
    locked = tuple(targets)
    target_commitment_sha256(locked)
    return locked


def _parse_strict_target_output(
    output_path: Path,
    *,
    target_ids: tuple[str, ...],
    output_sha256: str,
) -> tuple[ReproducedCell, ...]:
    decoded = load_strict_reproduction_json(output_path)
    if not isinstance(decoded, dict) or set(decoded) != {"schema_version", "targets"}:
        raise ValueError("target-set output must contain exactly schema_version and targets")
    if decoded["schema_version"] != 1:
        raise ValueError("unsupported target-set output schema_version")
    rows = decoded["targets"]
    if not isinstance(rows, list):
        raise TypeError("target-set output targets must be an array")

    allowed = set(target_ids)
    seen: set[str] = set()
    cells: list[ReproducedCell] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"target_id", "value"}:
            raise ValueError("each target-set output row must contain exactly target_id and value")
        target_id = row["target_id"]
        value = row["value"]
        if not isinstance(target_id, str) or target_id not in allowed:
            raise ValueError(f"unexpected target-set output target_id: {target_id!r}")
        if target_id in seen:
            raise ValueError(f"duplicate target-set output target_id: {target_id!r}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"target {target_id!r} must contain one finite numeric value")
        numeric = finite_reproduction_float(
            value,
            label=f"target {target_id!r}",
        )
        seen.add(target_id)
        cells.append(ReproducedCell(target_id, numeric, output_sha256))
    return tuple(cells)


def _validate_target_set_contract(
    packet: Mapping[str, Any],
    targets: tuple[ReproductionTarget, ...],
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...], str]:
    contract = packet.get("target_set_contract")
    if not isinstance(contract, Mapping):
        raise TypeError("target_set_contract must be an object")
    rows = contract.get("targets")
    if not isinstance(rows, list) or not rows:
        raise ValueError("target_set_contract requires at least one target")
    if len(rows) != len(targets):
        raise ValueError("private target count does not match the locked target-set contract")

    observed_commitment = target_commitment_sha256(targets)
    _require_equal(
        "target-set commitment",
        observed_commitment,
        contract.get("target_commitment_sha256"),
    )
    _require_equal(
        "target-set output format",
        contract.get("reproduced_values_format"),
        "strict_target_json_v1",
    )

    normalized_rows: list[Mapping[str, Any]] = []
    for target, row in zip(targets, rows, strict=True):
        if not isinstance(row, Mapping):
            raise TypeError("target_set_contract target rows must be objects")
        _require_equal("target id", target.target_id, row.get("target_id"))
        _require_equal("claim id", target.claim_id, row.get("claim_id"))
        _require_equal("target metric", target.metric, row.get("metric"))
        normalized_rows.append(row)
    return contract, tuple(normalized_rows), observed_commitment


def _claim_summaries(
    targets: tuple[ReproductionTarget, ...],
    comparisons: tuple[CellComparison, ...],
    output_sha256: str,
) -> list[dict[str, Any]]:
    by_claim: dict[str, list[tuple[ReproductionTarget, CellComparison]]] = {}
    for target, comparison in zip(targets, comparisons, strict=True):
        by_claim.setdefault(target.claim_id, []).append((target, comparison))

    summaries: list[dict[str, Any]] = []
    for claim_id, rows in by_claim.items():
        claim_report = build_reproduction_report(
            tuple(comparison for _, comparison in rows),
            authority=ReproductionAuthority.AUTHOR_PACKAGE_RERUN,
            method_fidelity_verified=False,
            artifact_identity_verified=True,
            execution_attested=True,
        )
        summaries.append(
            {
                "claim_id": claim_id,
                "decision": claim_report.decision.value.upper(),
                "targets": [
                    {
                        "target_id": target.target_id,
                        "metric": comparison.metric,
                        "status": comparison.status.value.upper(),
                        "output_artifact_bound": comparison.output_artifact_sha256 == output_sha256,
                    }
                    for target, comparison in rows
                ],
            }
        )
    return summaries


def build_answer_free_reproduction_target_set_certificate(
    *,
    packet: Mapping[str, Any],
    execution: Mapping[str, Any],
    private_targets: tuple[ReproductionTarget, ...],
    output_path: str | Path,
) -> dict[str, Any]:
    """Compare a frozen target-set output while keeping all paper numeric answers secret."""

    if not private_targets:
        raise ValueError("target-set ingest requires at least one private target")
    validate_target_set_ingest_contract(packet, execution)
    output = Path(output_path)
    output_sha256 = _validate_execution_evidence(packet, execution, output)
    contract, target_contracts, observed_commitment = _validate_target_set_contract(
        packet,
        private_targets,
    )

    target_ids = tuple(target.target_id for target in private_targets)
    execution_target_ids = execution.get("target_ids")
    if not isinstance(execution_target_ids, list):
        raise TypeError("target-set execution must attest an ordered target_ids array")
    _require_equal("execution target ids", tuple(execution_target_ids), target_ids)

    reproduced = _parse_strict_target_output(
        output,
        target_ids=target_ids,
        output_sha256=output_sha256,
    )
    comparisons = compare_reproduced_cells(private_targets, reproduced)
    report = build_reproduction_report(
        comparisons,
        authority=ReproductionAuthority.AUTHOR_PACKAGE_RERUN,
        method_fidelity_verified=False,
        artifact_identity_verified=True,
        execution_attested=True,
    )

    reviews = [
        {
            "target_id": target.target_id,
            "reviewer_a_complete": bool(row.get("reviewer_a_complete")),
            "reviewer_b_complete": bool(row.get("reviewer_b_complete")),
            "adjudication_complete": bool(row.get("adjudication_complete")),
        }
        for target, row in zip(private_targets, target_contracts, strict=True)
    ]
    present_comparisons = [item for item in report.comparisons if item.output_artifact_sha256 is not None]

    return {
        "schema_version": 2,
        "case_id": packet["case_id"],
        "track": "author_package_frozen_environment_rerun",
        "status": "descriptive_target_set_comparison_pending_independent_review",
        "target_set": {
            "target_ids": list(target_ids),
            "target_commitment_sha256": observed_commitment,
            "reported_numeric_values_stored_in_certificate": False,
            "post_run_unseal_checked_by_veritas": True,
            "reproduced_values_format": contract["reproduced_values_format"],
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
            "total_targets": report.agreement.total_targets,
            "matched_targets": report.agreement.matched_targets,
            "mismatched_targets": report.agreement.mismatched_targets,
            "missing_targets": report.agreement.missing_targets,
            "target_commitment_validated": True,
            "all_present_outputs_artifact_bound": all(
                item.output_artifact_sha256 == output_sha256 for item in present_comparisons
            ),
            "numeric_values_persisted_in_certificate": False,
        },
        "claims": _claim_summaries(private_targets, report.comparisons, output_sha256),
        "review": {
            "targets": reviews,
            "all_targets_double_reviewed": all(
                row["reviewer_a_complete"] and row["reviewer_b_complete"] for row in reviews
            ),
            "all_targets_adjudicated": all(row["adjudication_complete"] for row in reviews),
            "method_fidelity_independent_complete": False,
        },
        "authority": {
            "production_authorized": False,
            "e4_authorized": False,
            "max_evidence_grade": report.max_evidence_grade.name,
            "reasons": list(report.reasons),
        },
    }


def build_answer_free_target_set_certificate_from_files(
    *,
    packet_path: str | Path,
    execution_path: str | Path,
    private_targets_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    packet = load_strict_reproduction_json(packet_path)
    execution = load_strict_reproduction_json(execution_path)
    targets = load_private_reproduction_target_set(private_targets_path)
    return build_answer_free_reproduction_target_set_certificate(
        packet=packet,
        execution=execution,
        private_targets=targets,
        output_path=output_path,
    )
