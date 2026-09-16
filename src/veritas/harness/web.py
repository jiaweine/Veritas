from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .benchmark_catalog import benchmark_catalog
from .parser_stack import parser_stack_capability
from .run_views import project_run_detail
from .service import AuditHarness
from .telemetry import telemetry_capability

MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 80 * 1024 * 1024


class MessageRequest(BaseModel):
    message: str


class ReplicationRequest(BaseModel):
    prompt: str


def _cors_origins() -> list[str]:
    configured = os.environ.get("VERITAS_CORS_ORIGINS", "").strip()
    if not configured:
        return []
    return [value.strip() for value in configured.split(",") if value.strip()]


def create_app(
    data_dir: str | Path | None = None,
    *,
    harness: AuditHarness | None = None,
) -> FastAPI:
    resolved_data_dir = Path(
        data_dir or os.environ.get("VERITAS_HARNESS_DATA", "~/.veritas/harness")
    ).expanduser()
    runtime = harness or AuditHarness(resolved_data_dir)
    static_dir = Path(__file__).with_name("static")

    app = FastAPI(
        title="Veritas Research Audit Harness",
        version="0.6.0",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.harness = runtime

    origins = _cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Accept"],
        )

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "veritas-harness", "api_version": "v1"}

    @app.get("/api/v1/capabilities")
    def capabilities() -> dict[str, object]:
        value = dict(runtime.capabilities())
        value["max_attachment_bytes"] = MAX_ATTACHMENT_BYTES
        value["parser_stack"] = parser_stack_capability()
        value["observability"] = telemetry_capability()
        return value

    @app.get("/api/v1/overview")
    def overview() -> dict[str, object]:
        return runtime.overview()

    @app.get("/api/v1/findings")
    def findings() -> list[dict[str, object]]:
        return runtime.findings()

    @app.get("/api/v1/benchmarks")
    def benchmarks() -> dict[str, object]:
        return benchmark_catalog()

    @app.get("/api/v1/runs")
    def runs() -> list[dict[str, object]]:
        return runtime.runs()

    @app.get("/api/v1/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        detail = project_run_detail(runtime.list_audits(), run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        return detail

    @app.get("/api/v1/search")
    def search(
        q: Annotated[str, Query(min_length=1, max_length=200)],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> list[dict[str, object]]:
        return runtime.search(q, limit=limit)

    @app.get("/api/audits")
    @app.get("/api/v1/audits")
    def list_audits() -> list[dict[str, object]]:
        return runtime.list_audits()

    @app.get("/api/audits/{audit_id}")
    @app.get("/api/v1/audits/{audit_id}")
    def get_audit(audit_id: str) -> dict[str, object]:
        try:
            return runtime.get_audit(audit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/audits")
    @app.post("/api/v1/audits")
    async def create_audit(
        file: Annotated[UploadFile, File()],
        title: Annotated[str, Form()] = "",
    ) -> dict[str, object]:
        payload = await file.read()
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="PDF exceeds the 80 MiB local harness limit")
        try:
            return runtime.create_audit(
                title=title,
                filename=file.filename or "paper.pdf",
                pdf_bytes=payload,
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/audits/{audit_id}/paper")
    @app.get("/api/v1/audits/{audit_id}/paper")
    def paper(audit_id: str) -> FileResponse:
        try:
            path = runtime.paper_path(audit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(
            path,
            media_type="application/pdf",
            filename="paper.pdf",
            content_disposition_type="inline",
        )

    @app.get("/api/v1/audits/{audit_id}/attachments")
    def list_attachments(audit_id: str) -> list[dict[str, object]]:
        try:
            return runtime.list_attachments(audit_id)
        except (FileNotFoundError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/audits/{audit_id}/attachments")
    async def add_attachment(
        audit_id: str,
        file: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        try:
            runtime.get_audit(audit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        payload = await file.read()
        if len(payload) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=413,
                detail="attachment exceeds the 80 MiB local harness limit",
            )
        try:
            return runtime.add_attachment(
                audit_id,
                filename=file.filename or "artifact.bin",
                payload=payload,
                media_type=file.content_type,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/audits/{audit_id}/attachments/{attachment_id}")
    def attachment(audit_id: str, attachment_id: str) -> FileResponse:
        try:
            path = runtime.store.get_attachment_path(audit_id, attachment_id)
        except (FileNotFoundError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=path.name,
            content_disposition_type="attachment",
        )

    @app.post("/api/audits/{audit_id}/messages")
    @app.post("/api/v1/audits/{audit_id}/messages")
    def send_message(audit_id: str, request: MessageRequest) -> StreamingResponse:
        if not request.message.strip():
            raise HTTPException(status_code=422, detail="message must not be empty")
        try:
            runtime.get_audit(audit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        def stream() -> Iterator[bytes]:
            for event in runtime.stream_message(audit_id, request.message):
                yield (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/api/v1/audits/{audit_id}/replication")
    async def run_replication(
        audit_id: str,
        request: ReplicationRequest,
    ) -> StreamingResponse:
        if not request.prompt.strip():
            raise HTTPException(status_code=422, detail="replication prompt must not be empty")
        try:
            runtime.get_audit(audit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not runtime.replication_capability()["configured"]:
            raise HTTPException(
                status_code=503,
                detail="replication agent is not configured on the Veritas server",
            )

        async def stream() -> AsyncIterator[bytes]:
            async for event in runtime.stream_replication(audit_id, request.prompt):
                yield (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        return FileResponse(static_dir / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        return FileResponse(static_dir / "sw.js", media_type="application/javascript")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return app
