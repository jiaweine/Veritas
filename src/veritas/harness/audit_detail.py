from __future__ import annotations

import json
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from .service import AuditHarness

DEFAULT_PRODUCT_EVENT_LIMIT = 24
MAX_PRODUCT_EVENT_LIMIT = 200


def register_audit_detail_routes(app: FastAPI, runtime: AuditHarness) -> None:
    """Expose a bounded audit detail projection for interactive product clients.

    The legacy audit detail route remains fully hydrated for compatibility. Web
    and mobile clients use this route so long append-only event journals never
    become unbounded response payloads or Python event lists.
    """

    @app.get("/api/v1/audits/{audit_id}/product-detail")
    def audit_product_detail(
        audit_id: str,
        event_limit: Annotated[int, Query(ge=1, le=MAX_PRODUCT_EVENT_LIMIT)] = DEFAULT_PRODUCT_EVENT_LIMIT,
    ) -> dict[str, object]:
        if not audit_id.startswith("audit_") or not audit_id[6:].isalnum():
            raise HTTPException(status_code=404, detail=f"audit not found: {audit_id}")
        try:
            return runtime.store.get_audit(audit_id, event_limit=event_limit)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"audit event history integrity error: {exc}",
            ) from exc
