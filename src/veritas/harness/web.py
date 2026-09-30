from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from . import web_core as _core
from .request_limits import RequestBodyLimitMiddleware
from .service import AuditHarness

MAX_UPLOAD_BYTES = _core.MAX_UPLOAD_BYTES
MAX_ATTACHMENT_BYTES = _core.MAX_ATTACHMENT_BYTES


def create_app(
    data_dir: str | Path | None = None,
    *,
    harness: AuditHarness | None = None,
) -> FastAPI:
    """Create the product app with an outer request-body guard.

    ``web_core`` owns the product/API surface. Keeping the guard in this thin
    wrapper lets the limit run before FastAPI/Starlette parses JSON or multipart
    request bodies while preserving the existing web module API.
    """

    app = _core.create_app(data_dir, harness=harness)

    @app.middleware("http")
    async def sync_compat_upload_limits(request: Request, call_next):
        # Existing callers/tests patch these public module constants. Mirror them
        # into the delegated core at request time so that contract remains intact.
        _core.MAX_UPLOAD_BYTES = MAX_UPLOAD_BYTES
        _core.MAX_ATTACHMENT_BYTES = MAX_ATTACHMENT_BYTES
        return await call_next(request)

    # Added last so the pure-ASGI guard remains outside BaseHTTP middleware and
    # therefore bounds the body before FastAPI/Starlette request parsing.
    app.add_middleware(RequestBodyLimitMiddleware)
    return app


def __getattr__(name: str) -> Any:
    return getattr(_core, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_core)))
