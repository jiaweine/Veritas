from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query

from .service import AuditHarness

_MAX_AUDIT_PAGE_SIZE = 200


def _project_audit_list_item(item: dict[str, Any]) -> dict[str, Any]:
    """Return the bounded list projection; event history stays on the detail API."""

    return {
        "audit_id": item.get("audit_id"),
        "title": item.get("title"),
        "filename": item.get("filename"),
        "status": item.get("status"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "artifact_sha256": item.get("artifact_sha256"),
        "paper_summary": item.get("paper_summary") or {},
        "latest_result": item.get("latest_result"),
        "notes_updated_at": item.get("notes_updated_at"),
    }


def register_audit_pagination_routes(app: FastAPI, runtime: AuditHarness) -> None:
    """Register the bounded Audit history feed without changing legacy list APIs."""

    @app.get("/api/v1/audit-pages")
    def audit_page(
        limit: Annotated[int, Query(ge=1, le=_MAX_AUDIT_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
    ) -> dict[str, Any]:
        projector = getattr(runtime, "audits_page", None)
        if callable(projector):
            try:
                page = projector(limit=limit, cursor=cursor)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {
                "items": [
                    _project_audit_list_item(item)
                    for item in page.get("items") or []
                    if isinstance(item, dict)
                ],
                "next_cursor": page.get("next_cursor"),
                "has_more": bool(page.get("has_more")),
                "total": int(page.get("total") or 0),
                "status_counts": dict(page.get("status_counts") or {}),
            }

        # Explicit custom/legacy runtimes keep their historical full-list behavior.
        # The compatibility fallback is intentionally offset based and opaque to clients.
        try:
            offset = int(cursor) if cursor is not None else 0
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="audit cursor is invalid") from exc
        if offset < 0:
            raise HTTPException(status_code=422, detail="audit cursor is invalid")

        values = [
            _project_audit_list_item(item)
            for item in runtime.list_audits()
            if isinstance(item, dict)
        ]
        counts = Counter(str(item.get("status") or "unknown") for item in values)
        items = values[offset : offset + limit]
        next_offset = offset + len(items)
        has_more = next_offset < len(values)
        return {
            "items": items,
            "next_cursor": str(next_offset) if has_more else None,
            "has_more": has_more,
            "total": len(values),
            "status_counts": dict(counts),
        }
