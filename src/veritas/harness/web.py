from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI

from . import web_core as _core
from .request_limits import RequestBodyLimitMiddleware
from .service import AuditHarness

__all__ = sorted({name for name in dir(_core) if not name.startswith("_")} | {"create_app"})


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
    app.add_middleware(RequestBodyLimitMiddleware)
    return app


def __getattr__(name: str) -> Any:
    return getattr(_core, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_core)))
