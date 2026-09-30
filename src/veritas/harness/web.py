from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI

from . import web_core as _core
from .request_limits import RequestBodyLimitMiddleware
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
    """Create the product app with an outer request-body guard.

    ``web_core`` owns the product/API surface. Keeping the guard in this thin
    wrapper lets the limit run before FastAPI/Starlette parses JSON or multipart
    request bodies while preserving the existing web module API.
    """

    app = _core.create_app(data_dir, harness=harness)
    app.add_middleware(_CompatRequestBodyLimitMiddleware)
    return app


def __getattr__(name: str) -> Any:
    return getattr(_core, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_core)))
