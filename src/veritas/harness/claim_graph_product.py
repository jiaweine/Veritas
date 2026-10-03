from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from veritas.claim_reconstruction import (
    ClaimObjectReconstructionError,
    reconstruct_statistical_object,
)
from veritas.claims import StatisticalClaimGraph


def _check_field(check_id: object) -> str | None:
    value = str(check_id or "").strip().lower()
    if value == "p_value" or "p_value" in value:
        return "p_value"
    if value == "se_positive" or "standard_error" in value:
        return "se"
    if value == "beta_se_t" or "t_stat" in value:
        return "t_stat"
    if value == "confidence_interval" or "confidence_interval" in value:
        return "ci_lower"
    return None


def _detector_annotations(result: dict[str, Any]) -> list[dict[str, object]]:
    """Return UI navigation annotations without mutating graph semantics."""

    annotations: list[dict[str, object]] = []
    for check in result.get("checks") or []:
        if not isinstance(check, dict):
            continue
        finding = check.get("finding")
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("finding_id") or "").strip()
        field = _check_field(check.get("check_id"))
        if not finding_id or field is None:
            continue
        source = finding.get("source") if isinstance(finding.get("source"), dict) else {}
        annotations.append(
            {
                "kind": "detector_finding",
                "finding_id": finding_id,
                "finding_title": str(finding.get("title") or "Finding")[:500],
                "explanation": str(finding.get("explanation") or "")[:4000],
                "severity": str(finding.get("severity") or "review")[:80],
                "check_id": str(check.get("check_id") or "")[:160],
                "status": str(check.get("status") or "")[:80],
                "field": field,
                "source": source,
                "graph_edge": False,
            }
        )
    return annotations


def project_claim_graph(record: dict[str, Any]) -> dict[str, object]:
    """Project one persisted StatisticalClaimGraph without inventing missing semantics."""

    audit_id = str(record.get("audit_id") or "")
    result = record.get("latest_result")
    if not isinstance(result, dict):
        return _unavailable(
            audit_id,
            state="no_audit_result",
            reason=(
                "This audit has no persisted result, so there is no StatisticalClaimGraph "
                "to inspect."
            ),
        )

    payload = result.get("claim_graph")
    if payload is None:
        return _unavailable(
            audit_id,
            state="not_persisted",
            reason=(
                "This audit result predates persisted StatisticalClaimGraph output. "
                "Veritas will not infer claim-object edges from detector checks or findings."
            ),
        )
    if not isinstance(payload, dict):
        return _unavailable(
            audit_id,
            state="invalid",
            reason=(
                "The persisted claim graph is not a valid object; Veritas refuses to render "
                "an inferred replacement."
            ),
        )

    try:
        graph = StatisticalClaimGraph.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        return _unavailable(
            audit_id,
            state="invalid",
            reason=(
                "The persisted claim graph failed validation; Veritas refuses to render an "
                "inferred replacement."
            ),
            validation_error=type(exc).__name__,
        )

    reconstruction: dict[str, dict[str, object]] = {}
    for object_id in graph.objects:
        try:
            reconstruct_statistical_object(graph, object_id)
        except ClaimObjectReconstructionError as exc:
            reconstruction[object_id] = {
                "available": False,
                "reason": str(exc)[:500],
            }
        else:
            reconstruction[object_id] = {"available": True, "reason": None}

    annotations = _detector_annotations(result)
    return {
        "audit_id": audit_id,
        "available": True,
        "state": "available",
        "reason": None,
        "authority": {
            "source": "persisted_statistical_claim_graph",
            "client_inferred_edges": False,
            "publication_claim_bound": bool(graph.claims),
            "claim_edges_persisted": len(graph.edges),
            "detector_annotations_are_graph_edges": False,
        },
        "counts": {
            "artifacts": len(graph.artifacts),
            "claims": len(graph.claims),
            "objects": len(graph.objects),
            "evidence_nodes": len(graph.evidence_nodes),
            "edges": len(graph.edges),
            "detector_annotations": len(annotations),
        },
        "reconstruction": reconstruction,
        "annotations": annotations,
        "graph": graph.to_dict(),
    }


def _unavailable(
    audit_id: str,
    *,
    state: str,
    reason: str,
    validation_error: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "audit_id": audit_id,
        "available": False,
        "state": state,
        "reason": reason,
        "authority": {
            "source": "persisted_statistical_claim_graph",
            "client_inferred_edges": False,
            "publication_claim_bound": False,
            "claim_edges_persisted": 0,
            "detector_annotations_are_graph_edges": False,
        },
        "counts": {
            "artifacts": 0,
            "claims": 0,
            "objects": 0,
            "evidence_nodes": 0,
            "edges": 0,
            "detector_annotations": 0,
        },
        "reconstruction": {},
        "annotations": [],
        "graph": None,
    }
    if validation_error is not None:
        payload["validation_error"] = validation_error
    return payload


def register_claim_graph_routes(app: FastAPI, harness: object) -> None:
    @app.get("/api/v1/audits/{audit_id}/claim-graph")
    def audit_claim_graph(audit_id: str) -> dict[str, object]:
        try:
            record = harness.get_audit(audit_id)  # type: ignore[attr-defined]
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return project_claim_graph(record)
