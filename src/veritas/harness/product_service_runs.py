from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import Any

from .product_service import ProductAuditHarness as _BaseProductAuditHarness
from .product_store_runs import ProductHarnessStore, RunSortKey
from .tools import PaperToolbox

_INTEGRITY_ERRORS = (OSError, ValueError, TypeError, json.JSONDecodeError)
_RUN_CURSOR_VERSION = 1
_MAX_RUN_PAGE_SIZE = 200
_MAX_RUN_CURSOR_CHARS = 1024


class ProductAuditHarness(_BaseProductAuditHarness):
    """Product harness with validated terminal-run indexing and keyset pages."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        toolbox: PaperToolbox | None = None,
    ) -> None:
        super().__init__(data_dir, toolbox=toolbox)
        self.store = ProductHarnessStore(self.store.root)

    def runs(self) -> list[dict[str, Any]]:
        """Preserve the historical full-list API without rescanning warm journals."""

        audits = self._validated_audit_map()
        rows = self.store.terminal_runs(set(audits))
        return [self._decorate_run(item, audits) for item in rows]

    def runs_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("run page limit must be an integer")
        if limit < 1 or limit > _MAX_RUN_PAGE_SIZE:
            raise ValueError(f"run page limit must be between 1 and {_MAX_RUN_PAGE_SIZE}")
        after = self._decode_run_cursor(cursor)
        audits = self._validated_audit_map()
        items, has_more, next_key = self.store.terminal_run_page(
            set(audits),
            limit=limit,
            after=after,
        )
        return {
            "items": [self._decorate_run(item, audits) for item in items],
            "next_cursor": self._encode_run_cursor(next_key) if next_key is not None else None,
            "has_more": has_more,
        }

    def _validated_audit_map(self) -> dict[str, dict[str, Any]]:
        audits: dict[str, dict[str, Any]] = {}
        for audit in self._metadata_audits():
            audit_id = str(audit.get("audit_id") or "")
            if not audit_id:
                continue
            try:
                self.store.validate_events(audit_id)
            except _INTEGRITY_ERRORS:
                continue
            audits[audit_id] = audit
        return audits

    @staticmethod
    def _decorate_run(
        item: dict[str, Any],
        audits: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        value = dict(item)
        audit = audits.get(str(value.get("audit_id") or "")) or {}
        value["audit_title"] = audit.get("title")
        return value

    @staticmethod
    def _encode_run_cursor(key: RunSortKey) -> str:
        payload = json.dumps(
            {
                "v": _RUN_CURSOR_VERSION,
                "created_at": key[0],
                "run_id": key[1],
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_run_cursor(cursor: str | None) -> RunSortKey | None:
        if cursor is None:
            return None
        clean = str(cursor).strip()
        if not clean:
            return None
        if len(clean) > _MAX_RUN_CURSOR_CHARS:
            raise ValueError("run cursor is too long")
        padding = "=" * (-len(clean) % 4)
        try:
            raw = base64.b64decode(
                clean + padding,
                altchars=b"-_",
                validate=True,
            )
            value = json.loads(raw.decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("run cursor is invalid") from exc
        if not isinstance(value, dict) or value.get("v") != _RUN_CURSOR_VERSION:
            raise ValueError("run cursor version is unsupported")
        created_at = value.get("created_at")
        run_id = value.get("run_id")
        if not isinstance(created_at, str) or not isinstance(run_id, str):
            raise ValueError("run cursor payload is invalid")
        if not run_id or len(run_id) > 512 or len(created_at) > 128:
            raise ValueError("run cursor payload is invalid")
        return created_at, run_id
