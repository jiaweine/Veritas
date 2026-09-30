from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

_DEFAULT_API_BODY_BYTES = 256 * 1024
_DEFAULT_UPLOAD_ENVELOPE_BYTES = 82 * 1024 * 1024
_BODY_METHODS = {"POST", "PUT", "PATCH"}

ASGIMessage = dict[str, Any]
Receive = Callable[[], Awaitable[ASGIMessage]]
Send = Callable[[ASGIMessage], Awaitable[None]]
ASGIApp = Callable[[dict[str, Any], Receive, Send], Awaitable[None]]


class _BodyLimitExceeded(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Bound API request bodies before FastAPI parses JSON or multipart data.

    The file-level upload limits in ``web.py`` remain authoritative for paper
    and attachment bytes. This middleware limits the *entire HTTP envelope* so
    a client cannot make Starlette buffer arbitrarily large JSON or multipart
    bodies before those route-level checks run.

    Both declared ``Content-Length`` and streamed/chunked bodies are enforced.
    Upload endpoints receive a larger envelope budget to accommodate the
    configured 80 MiB file limit plus multipart headers/form fields.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit: int = _DEFAULT_API_BODY_BYTES,
        upload_limit: int = _DEFAULT_UPLOAD_ENVELOPE_BYTES,
    ) -> None:
        if default_limit <= 0 or upload_limit <= 0:
            raise ValueError("request body limits must be positive")
        if upload_limit < default_limit:
            raise ValueError("upload request limit must not be smaller than the default limit")
        self.app = app
        self.default_limit = int(default_limit)
        self.upload_limit = int(upload_limit)

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method") or "").upper()
        path = str(scope.get("path") or "")
        if method not in _BODY_METHODS or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        limit = self.upload_limit if _is_upload_endpoint(path, method) else self.default_limit
        headers = list(scope.get("headers") or [])
        try:
            content_length = _content_length(headers)
        except ValueError:
            await _send_json(send, 400, "invalid Content-Length header")
            return

        if content_length is not None and content_length > limit:
            await _send_json(send, 413, _limit_detail(limit))
            return

        received = 0
        response_started = False

        async def limited_receive() -> ASGIMessage:
            nonlocal received
            message = await receive()
            if message.get("type") != "http.request":
                return message
            body = message.get("body", b"")
            if not isinstance(body, (bytes, bytearray, memoryview)):
                raise _BodyLimitExceeded
            received += len(body)
            if received > limit:
                raise _BodyLimitExceeded
            return message

        async def tracking_send(message: ASGIMessage) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyLimitExceeded:
            if response_started:
                raise
            await _send_json(send, 413, _limit_detail(limit))


def _is_upload_endpoint(path: str, method: str) -> bool:
    if method != "POST":
        return False
    parts = path.strip("/").split("/")
    if parts in (["api", "audits"], ["api", "v1", "audits"]):
        return True
    return (
        len(parts) == 5
        and parts[:3] == ["api", "v1", "audits"]
        and bool(parts[3])
        and parts[4] == "attachments"
    )


def _content_length(headers: list[tuple[bytes, bytes]]) -> int | None:
    values = [value for key, value in headers if key.lower() == b"content-length"]
    if not values:
        return None
    if len(values) != 1:
        raise ValueError("duplicate Content-Length")
    try:
        text = values[0].decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("non-ASCII Content-Length") from exc
    if not text or not text.isdecimal():
        raise ValueError("malformed Content-Length")
    value = int(text)
    if value < 0:
        raise ValueError("negative Content-Length")
    return value


def _limit_detail(limit: int) -> str:
    return f"request body exceeds the {limit:,} byte API limit"


async def _send_json(send: Send, status: int, detail: str) -> None:
    payload = json.dumps({"detail": detail}, separators=(",", ":")).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload, "more_body": False})
