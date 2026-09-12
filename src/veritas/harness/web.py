from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .service import AuditHarness


class MessageRequest(BaseModel):
    message: str


def create_app(
    data_dir: str | Path | None = None,
    *,
    harness: AuditHarness | None = None,
) -> FastAPI:
    resolved_data_dir = Path(
        data_dir
        or os.environ.get("VERITAS_HARNESS_DATA", "~/.veritas/harness")
    ).expanduser()
    runtime = harness or AuditHarness(resolved_data_dir)
    static_dir = Path(__file__).with_name("static")

    app = FastAPI(
        title="Veritas Research Audit Harness",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.harness = runtime
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "veritas-harness"}

    @app.get("/api/audits")
    def list_audits() -> list[dict[str, object]]:
        return runtime.list_audits()

    @app.get("/api/audits/{audit_id}")
    def get_audit(audit_id: str) -> dict[str, object]:
        try:
            return runtime.get_audit(audit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/audits")
    async def create_audit(
        file: UploadFile = File(...),
        title: str = Form(""),
    ) -> dict[str, object]:
        payload = await file.read()
        if len(payload) > 80 * 1024 * 1024:
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

    @app.post("/api/audits/{audit_id}/messages")
    def send_message(audit_id: str, request: MessageRequest) -> StreamingResponse:
        try:
            runtime.get_audit(audit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        def stream() -> Iterator[bytes]:
            for event in runtime.stream_message(audit_id, request.message):
                yield (
                    json.dumps(event, ensure_ascii=False, sort_keys=True)
                    + "\n"
                ).encode("utf-8")

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return app
