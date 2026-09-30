from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .models import HarnessEvent
from .run_views import project_run_detail

MAX_REPLICATION_REVIEW_NOTE_CHARS = 4_000
ReplicationReviewDisposition = Literal["supports", "contradicts", "inconclusive"]


class ReplicationReviewRequest(BaseModel):
    disposition: ReplicationReviewDisposition
    note: str = Field(default="", max_length=MAX_REPLICATION_REVIEW_NOTE_CHARS)


def _run_detail(runtime: Any, run_id: str) -> dict[str, Any]:
    detail = project_run_detail(runtime.list_audits(), run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="run not found")
    if detail.get("run_kind") != "replication":
        raise HTTPException(status_code=422, detail="review is only available for replication runs")
    return detail


def _origin_finding(detail: dict[str, Any]) -> dict[str, Any]:
    origin = detail.get("origin_finding")
    if not isinstance(origin, dict) or not origin.get("finding_id"):
        raise HTTPException(status_code=409, detail="replication run is not linked to a finding")
    return origin


def _review_payload(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("kind") != "replication_review":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    review = payload.get("review")
    if not isinstance(review, dict):
        return None
    return {
        **review,
        "event_id": event.get("event_id"),
        "created_at": event.get("created_at"),
    }


def _latest_review(detail: dict[str, Any]) -> dict[str, Any] | None:
    for event in reversed(detail.get("events") or []):
        if not isinstance(event, dict):
            continue
        review = _review_payload(event)
        if review is not None:
            return review
    return None


def register_replication_review_routes(app: FastAPI, runtime: Any) -> None:
    @app.get("/api/v1/runs/{run_id}/review")
    def get_replication_review(run_id: str) -> dict[str, Any]:
        detail = _run_detail(runtime, run_id)
        origin = _origin_finding(detail)
        return {
            "run_id": run_id,
            "audit_id": detail.get("audit_id"),
            "origin_finding": origin,
            "review": _latest_review(detail),
            "review_only": True,
            "does_not_resolve_finding": True,
            "does_not_promote_evidence": True,
        }

    @app.post("/api/v1/runs/{run_id}/review")
    def record_replication_review(
        run_id: str,
        request: ReplicationReviewRequest,
    ) -> dict[str, Any]:
        detail = _run_detail(runtime, run_id)
        origin = _origin_finding(detail)
        if detail.get("phase") not in {"finish", "error"}:
            raise HTTPException(status_code=409, detail="replication run is not terminal")

        note = request.note.strip()
        finding_id = str(origin["finding_id"])
        review = {
            "disposition": request.disposition,
            "note": note,
            "finding_id": finding_id,
            "review_only": True,
            "does_not_resolve_finding": True,
            "does_not_promote_evidence": True,
        }
        event = HarnessEvent(
            audit_id=str(detail["audit_id"]),
            kind="replication_review",
            title="Replication review recorded",
            detail=(
                f"Operator marked the linked reproduction as {request.disposition}. "
                "Review-only annotation; detector evidence and finding state are unchanged."
            ),
            status="info",
            payload={
                "tool": "replication.review",
                "run_kind": "replication",
                "run_id": run_id,
                "phase": "review",
                "review": review,
            },
        )
        runtime.store.append_event(event)
        return {
            "run_id": run_id,
            "audit_id": detail.get("audit_id"),
            "origin_finding": origin,
            "review": {
                **review,
                "event_id": event.event_id,
                "created_at": event.created_at,
            },
            "review_only": True,
            "does_not_resolve_finding": True,
            "does_not_promote_evidence": True,
        }
