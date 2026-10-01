from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query

from .replication_workspace_product import normalize_replication_run
from .service import AuditHarness

_MAX_RUN_PAGE_SIZE = 200


def register_run_pagination_routes(app: FastAPI, runtime: AuditHarness) -> None:
    """Register the bounded Runs feed without changing the legacy list contract."""

    @app.get("/api/v1/run-pages")
    def run_page(
        limit: Annotated[int, Query(ge=1, le=_MAX_RUN_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
    ) -> dict[str, Any]:
        projector = getattr(runtime, "runs_page", None)
        if callable(projector):
            try:
                page = projector(limit=limit, cursor=cursor)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {
                "items": [normalize_replication_run(item) for item in page.get("items") or []],
                "next_cursor": page.get("next_cursor"),
                "has_more": bool(page.get("has_more")),
            }

        # Explicitly supplied legacy/custom Harness runtimes keep working. Their
        # fallback cursor is intentionally an opaque decimal offset; callers must
        # never infer or depend on either cursor representation.
        try:
            offset = int(cursor) if cursor is not None else 0
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="run cursor is invalid") from exc
        if offset < 0:
            raise HTTPException(status_code=422, detail="run cursor is invalid")
        values = [normalize_replication_run(item) for item in runtime.runs()]
        items = values[offset : offset + limit]
        next_offset = offset + len(items)
        has_more = next_offset < len(values)
        return {
            "items": items,
            "next_cursor": str(next_offset) if has_more else None,
            "has_more": has_more,
        }
