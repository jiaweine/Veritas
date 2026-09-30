from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi.testclient import TestClient

from veritas.harness.request_limits import RequestBodyLimitMiddleware
from veritas.harness.web import create_app

ASGIMessage = dict[str, Any]


def test_large_json_body_is_rejected_before_route_processing(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    oversized = "x" * (300 * 1024)

    response = client.post(
        "/api/v1/audits/not-a-real-audit/messages",
        content=json.dumps({"message": oversized}),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert "262,144 byte API limit" in response.json()["detail"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/audits").json() == []


def test_streamed_body_without_content_length_is_bounded() -> None:
    called = False

    async def app(scope, receive, send) -> None:
        nonlocal called
        called = True
        while True:
            message = await receive()
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    middleware = RequestBodyLimitMiddleware(app, default_limit=8, upload_limit=32)
    responses = _run_asgi(
        middleware,
        path="/api/v1/audits/a/messages",
        chunks=[b"12345", b"6789"],
    )

    assert called is True
    assert responses[0]["status"] == 413
    assert b"8 byte API limit" in responses[1]["body"]


def test_upload_route_receives_larger_envelope_budget() -> None:
    received = bytearray()

    async def app(scope, receive, send) -> None:
        while True:
            message = await receive()
            received.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    middleware = RequestBodyLimitMiddleware(app, default_limit=8, upload_limit=32)
    responses = _run_asgi(
        middleware,
        path="/api/v1/audits/audit_abc/attachments",
        chunks=[b"0123456789abcdef"],
    )

    assert bytes(received) == b"0123456789abcdef"
    assert responses[0]["status"] == 204


def test_declared_oversize_body_is_rejected_without_reading_receive() -> None:
    app_called = False
    receive_called = False

    async def app(scope, receive, send) -> None:
        nonlocal app_called
        app_called = True
        await receive()

    async def receive() -> ASGIMessage:
        nonlocal receive_called
        receive_called = True
        return {"type": "http.request", "body": b"", "more_body": False}

    responses: list[ASGIMessage] = []

    async def send(message: ASGIMessage) -> None:
        responses.append(message)

    middleware = RequestBodyLimitMiddleware(app, default_limit=8, upload_limit=32)
    scope = _scope(
        path="/api/v1/audits/a/messages",
        headers=[(b"content-length", b"9")],
    )
    _run(middleware(scope, receive, send))

    assert app_called is False
    assert receive_called is False
    assert responses[0]["status"] == 413


def test_malformed_or_duplicate_content_length_fails_closed() -> None:
    async def app(scope, receive, send) -> None:
        raise AssertionError("invalid content length must not reach the app")

    middleware = RequestBodyLimitMiddleware(app, default_limit=8, upload_limit=32)

    malformed = _run_asgi(
        middleware,
        path="/api/v1/audits/a/messages",
        chunks=[b"x"],
        headers=[(b"content-length", b"nope")],
    )
    duplicate = _run_asgi(
        middleware,
        path="/api/v1/audits/a/messages",
        chunks=[b"x"],
        headers=[(b"content-length", b"1"), (b"content-length", b"1")],
    )

    assert malformed[0]["status"] == 400
    assert duplicate[0]["status"] == 400
    assert b"invalid Content-Length" in malformed[1]["body"]


def _scope(
    *,
    path: str,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers or [],
        "client": ("test", 1234),
        "server": ("testserver", 80),
    }


def _run_asgi(
    app: Callable[
        [dict[str, Any], Callable[[], Awaitable[ASGIMessage]], Callable[[ASGIMessage], Awaitable[None]]],
        Awaitable[None],
    ],
    *,
    path: str,
    chunks: list[bytes],
    headers: list[tuple[bytes, bytes]] | None = None,
) -> list[ASGIMessage]:
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    if not messages:
        messages = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive() -> ASGIMessage:
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    responses: list[ASGIMessage] = []

    async def send(message: ASGIMessage) -> None:
        responses.append(message)

    _run(app(_scope(path=path, headers=headers), receive, send))
    return responses


def _run(awaitable: Awaitable[None]) -> None:
    import asyncio

    asyncio.run(awaitable)
