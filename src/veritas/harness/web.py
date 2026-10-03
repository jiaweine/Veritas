from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from . import web_core as _core
from .audit_pagination import register_audit_pagination_routes
from .claim_graph_product import register_claim_graph_routes
from .model_providers import register_model_provider_routes
from .product_service_runs import ProductAuditHarness
from .replication_review import register_replication_review_routes
from .request_limits import RequestBodyLimitMiddleware
from .run_pagination import register_run_pagination_routes
from .service import AuditHarness

MAX_UPLOAD_BYTES = _core.MAX_UPLOAD_BYTES
MAX_ATTACHMENT_BYTES = _core.MAX_ATTACHMENT_BYTES


class _CompatRequestBodyLimitMiddleware(RequestBodyLimitMiddleware):
    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        # Existing callers/tests patch these public module constants. Mirror them
        # into the delegated core before each request reaches route processing.
        _core.MAX_UPLOAD_BYTES = MAX_UPLOAD_BYTES
        _core.MAX_ATTACHMENT_BYTES = MAX_ATTACHMENT_BYTES
        await super().__call__(scope, receive, send)


def create_app(
    data_dir: str | Path | None = None,
    *,
    harness: AuditHarness | None = None,
) -> FastAPI:
    """Create the product app with bounded derived views and a body guard.

    ``web_core`` owns the product/API surface. The default runtime uses
    ``ProductAuditHarness`` so dashboard/search/run projections never hydrate
    every audit history at once. Explicitly supplied Harness instances remain
    untouched for embedding and backwards compatibility.
    """

    resolved_data_dir = Path(
        data_dir or os.environ.get("VERITAS_HARNESS_DATA", "~/.veritas/harness")
    ).expanduser()
    runtime = harness or ProductAuditHarness(resolved_data_dir)
    app = _core.create_app(resolved_data_dir, harness=runtime)
    register_model_provider_routes(app)
    register_replication_review_routes(app, app.state.harness)
    register_run_pagination_routes(app, app.state.harness)
    register_audit_pagination_routes(app, app.state.harness)
    register_claim_graph_routes(app, app.state.harness)
    app.add_middleware(_CompatRequestBodyLimitMiddleware)
    return app


def __getattr__(name: str) -> Any:
    return getattr(_core, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_core)))
