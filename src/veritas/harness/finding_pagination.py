from __future__ import annotations

import base64
import binascii
import json
from collections import Counter
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query

from .service import AuditHarness

_INTEGRITY_ERRORS = (OSError, ValueError, TypeError, json.JSONDecodeError)
_FINDING_CURSOR_VERSION = 1
_MAX_FINDING_PAGE_SIZE = 200
_MAX_FINDING_CURSOR_CHARS = 1024
FindingSortKey = tuple[str, str, int]


def _finding_sort_key(audit: dict[str, Any], index: int) -> FindingSortKey:
    return (
        str(audit.get("updated_at") or ""),
        str(audit.get("audit_id") or ""),
        -index,
    )


def _project_finding(
    audit: dict[str, Any],
    finding: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    result = audit.get("latest_result") or {}
    source = result.get("source") or {}
    return {
        "finding_id": f'{audit["audit_id"]}:finding:{index}',
        "audit_id": audit["audit_id"],
        "audit_title": audit.get("title"),
        "title": finding.get("title") or "Finding",
        "explanation": finding.get("explanation") or "",
        "severity": finding.get("severity") or "contradiction",
        "source": finding.get("source") or source,
        "updated_at": audit.get("updated_at"),
    }


def _encode_cursor(key: FindingSortKey) -> str:
    payload = json.dumps(
        {
            "v": _FINDING_CURSOR_VERSION,
            "updated_at": key[0],
            "audit_id": key[1],
            "finding_index": -key[2],
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> FindingSortKey | None:
    if cursor is None:
        return None
    clean = str(cursor).strip()
    if not clean:
        return None
    if len(clean) > _MAX_FINDING_CURSOR_CHARS:
        raise ValueError("finding cursor is too long")
    padding = "=" * (-len(clean) % 4)
    try:
        raw = base64.b64decode(
            clean + padding,
            altchars=b"-_",
            validate=True,
        )
        value = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("finding cursor is invalid") from exc
    if not isinstance(value, dict) or value.get("v") != _FINDING_CURSOR_VERSION:
        raise ValueError("finding cursor version is unsupported")
    updated_at = value.get("updated_at")
    audit_id = value.get("audit_id")
    finding_index = value.get("finding_index")
    if (
        not isinstance(updated_at, str)
        or not isinstance(audit_id, str)
        or not isinstance(finding_index, int)
        or isinstance(finding_index, bool)
    ):
        raise TypeError("finding cursor payload is invalid")
    if (
        not audit_id
        or len(audit_id) > 256
        or len(updated_at) > 128
        or finding_index < 0
        or finding_index > 1_000_000
    ):
        raise ValueError("finding cursor payload is invalid")
    return updated_at, audit_id, -finding_index


def _product_page(
    runtime: AuditHarness,
    *,
    limit: int,
    cursor: str | None,
) -> dict[str, Any] | None:
    metadata_reader = getattr(runtime, "_metadata_audits", None)
    validator = getattr(getattr(runtime, "store", None), "validate_events", None)
    if not callable(metadata_reader) or not callable(validator):
        return None

    after = _decode_cursor(cursor)
    audits = [item for item in metadata_reader() if isinstance(item, dict)]
    audits.sort(
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("audit_id") or ""),
        ),
        reverse=True,
    )

    total = 0
    severity_counts: Counter[str] = Counter()
    page: list[tuple[FindingSortKey, dict[str, Any]]] = []

    for audit in audits:
        audit_id = str(audit.get("audit_id") or "")
        if not audit_id:
            continue
        try:
            validator(audit_id)
        except _INTEGRITY_ERRORS:
            continue

        result = audit.get("latest_result") or {}
        findings = result.get("findings") or []
        if not isinstance(findings, list):
            continue
        for index, finding in enumerate(findings):
            if not isinstance(finding, dict):
                continue
            total += 1
            severity = str(finding.get("severity") or "contradiction")
            severity_counts[severity] += 1
            key = _finding_sort_key(audit, index)
            if after is not None and key >= after:
                continue
            if len(page) <= limit:
                page.append((key, _project_finding(audit, finding, index)))

    has_more = len(page) > limit
    page = page[:limit]
    next_key = page[-1][0] if has_more and page else None
    return {
        "items": [item for _key, item in page],
        "next_cursor": _encode_cursor(next_key) if next_key is not None else None,
        "has_more": has_more,
        "total": total,
        "severity_counts": dict(severity_counts),
    }


def register_finding_pagination_routes(app: FastAPI, runtime: AuditHarness) -> None:
    """Register a bounded latest-result Finding feed without changing the legacy API."""

    @app.get("/api/v1/finding-pages")
    def finding_page(
        limit: Annotated[int, Query(ge=1, le=_MAX_FINDING_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
    ) -> dict[str, Any]:
        try:
            product = _product_page(runtime, limit=limit, cursor=cursor)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if product is not None:
            return product

        # Explicit custom/legacy runtimes keep their historical full-list behavior.
        # Their compatibility fallback is offset based and opaque to product clients.
        try:
            offset = int(cursor) if cursor is not None else 0
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="finding cursor is invalid") from exc
        if offset < 0:
            raise HTTPException(status_code=422, detail="finding cursor is invalid")

        values = [item for item in runtime.findings() if isinstance(item, dict)]
        items = values[offset : offset + limit]
        next_offset = offset + len(items)
        has_more = next_offset < len(values)
        counts = Counter(str(item.get("severity") or "contradiction") for item in values)
        return {
            "items": items,
            "next_cursor": str(next_offset) if has_more else None,
            "has_more": has_more,
            "total": len(values),
            "severity_counts": dict(counts),
        }
