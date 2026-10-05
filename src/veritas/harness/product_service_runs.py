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
_AUDIT_CURSOR_VERSION = 1
_MAX_RUN_PAGE_SIZE = 200
_MAX_AUDIT_PAGE_SIZE = 200
_MAX_RUN_CURSOR_CHARS = 1024
_MAX_AUDIT_CURSOR_CHARS = 1024
AuditSortKey = tuple[str, str]


class ProductAuditHarness(_BaseProductAuditHarness):
    """Product harness with validated keyset pages and warm product projections."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        toolbox: PaperToolbox | None = None,
    ) -> None:
        super().__init__(data_dir, toolbox=toolbox)
        self.store = ProductHarnessStore(self.store.root)

    def overview(self) -> dict[str, Any]:
        audits = self._metadata_audits()
        total_pages = 0
        running = 0
        verified = 0
        needs_review = 0
        contradictions = 0
        coverage_values: list[float] = []
        recent_activity: list[dict[str, Any]] = []
        coverage_series: list[dict[str, Any]] = []
        valid_audits: list[dict[str, Any]] = []

        for audit in audits:
            audit_id = str(audit.get("audit_id") or "")
            try:
                if len(recent_activity) < 8:
                    tail = self.store.validated_recent_event_tail(audit_id)
                else:
                    self.store.validate_events(audit_id)
                    tail = []
            except _INTEGRITY_ERRORS:
                continue

            valid_audits.append(audit)
            summary = audit.get("paper_summary") or {}
            total_pages += int(summary.get("pages") or 0)
            if audit.get("status") == "running":
                running += 1

            result = audit.get("latest_result") or {}
            counts = result.get("counts") or {}
            verified += int(counts.get("verified") or 0)
            needs_review += int(counts.get("needs_review") or 0)
            contradictions += int(counts.get("contradictions") or 0)
            if result:
                coverage = float(result.get("verification_coverage") or 0.0)
                coverage_values.append(coverage)
                coverage_series.append(
                    {
                        "audit_id": audit.get("audit_id"),
                        "title": audit.get("title"),
                        "coverage": coverage,
                        "updated_at": audit.get("updated_at"),
                    }
                )

            for event in reversed(tail):
                if len(recent_activity) >= 8:
                    break
                recent_activity.append(
                    {
                        "audit_id": audit.get("audit_id"),
                        "audit_title": audit.get("title"),
                        "event_id": event.get("event_id"),
                        "kind": event.get("kind"),
                        "title": event.get("title"),
                        "detail": event.get("detail"),
                        "status": event.get("status"),
                        "created_at": event.get("created_at"),
                    }
                )

        total_checks = verified + needs_review + contradictions
        verification_rate = (verified / total_checks) if total_checks else 0.0
        mean_coverage = (sum(coverage_values) / len(coverage_values)) if coverage_values else 0.0
        coverage_series = list(reversed(coverage_series[:12]))
        recent_activity.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)

        return {
            "audits_total": len(valid_audits),
            "audits_running": running,
            "papers_pages": total_pages,
            "checks_total": total_checks,
            "checks_verified": verified,
            "checks_review": needs_review,
            "checks_contradictions": contradictions,
            "verification_rate": verification_rate,
            "mean_coverage": mean_coverage,
            "findings_open": contradictions,
            "coverage_series": coverage_series,
            "recent_activity": recent_activity[:8],
            "updated_at": valid_audits[0].get("updated_at") if valid_audits else None,
        }

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Search validated metadata and bounded warm event-text projections.

        Matching preserves the historical case-folded substring semantics and
        result ordering. Warm event searches reuse only projections bound to a
        current full-journal validation watermark; oversized histories stream
        authoritatively instead of becoming unbounded cache entries.
        """

        needle = query.strip().casefold()
        if not needle or limit <= 0:
            return []
        results: list[dict[str, Any]] = []
        for audit in self._metadata_audits():
            remaining = limit - len(results)
            if remaining <= 0:
                return results[:limit]
            audit_text = " ".join(
                str(value or "")
                for value in (audit.get("title"), audit.get("filename"), audit.get("audit_id"))
            ).casefold()
            metadata_match = needle in audit_text
            event_limit = max(0, remaining - (1 if metadata_match else 0))
            audit_id = str(audit.get("audit_id") or "")
            try:
                documents = self.store.validated_search_matches(
                    audit_id,
                    needle,
                    limit=event_limit,
                )
            except _INTEGRITY_ERRORS:
                continue

            pending: list[dict[str, Any]] = []
            if metadata_match:
                pending.append(
                    {
                        "kind": "audit",
                        "id": audit.get("audit_id"),
                        "audit_id": audit.get("audit_id"),
                        "title": audit.get("title"),
                        "detail": audit.get("filename"),
                        "status": audit.get("status"),
                    }
                )
            pending.extend(
                {
                    "kind": "event",
                    "id": document.get("event_id"),
                    "audit_id": audit.get("audit_id"),
                    "title": document.get("title"),
                    "detail": document.get("detail"),
                    "status": document.get("status"),
                }
                for document in documents
            )
            results.extend(pending[:remaining])
            if len(results) >= limit:
                return results[:limit]
        return results[:limit]

    def audits_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("audit page limit must be an integer")
        if limit < 1 or limit > _MAX_AUDIT_PAGE_SIZE:
            raise ValueError(f"audit page limit must be between 1 and {_MAX_AUDIT_PAGE_SIZE}")

        after = self._decode_audit_cursor(cursor)
        audits = self._metadata_audits()
        audits.sort(key=self._audit_sort_key, reverse=True)
        status_counts: dict[str, int] = {}
        page: list[tuple[AuditSortKey, dict[str, Any]]] = []
        total = 0

        for audit in audits:
            audit_id = str(audit.get("audit_id") or "")
            if not audit_id:
                continue
            try:
                self.store.validate_events(audit_id)
            except _INTEGRITY_ERRORS:
                continue

            total += 1
            status = str(audit.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            key = self._audit_sort_key(audit)
            if after is not None and key >= after:
                continue
            if len(page) <= limit:
                page.append((key, audit))

        has_more = len(page) > limit
        page = page[:limit]
        next_key = page[-1][0] if has_more and page else None
        return {
            "items": [audit for _key, audit in page],
            "next_cursor": self._encode_audit_cursor(next_key) if next_key is not None else None,
            "has_more": has_more,
            "total": total,
            "status_counts": status_counts,
        }

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
    def _audit_sort_key(audit: dict[str, Any]) -> AuditSortKey:
        return str(audit.get("updated_at") or ""), str(audit.get("audit_id") or "")

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
    def _encode_audit_cursor(key: AuditSortKey) -> str:
        payload = json.dumps(
            {
                "v": _AUDIT_CURSOR_VERSION,
                "updated_at": key[0],
                "audit_id": key[1],
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_audit_cursor(cursor: str | None) -> AuditSortKey | None:
        if cursor is None:
            return None
        clean = str(cursor).strip()
        if not clean:
            return None
        if len(clean) > _MAX_AUDIT_CURSOR_CHARS:
            raise ValueError("audit cursor is too long")
        padding = "=" * (-len(clean) % 4)
        try:
            raw = base64.b64decode(
                clean + padding,
                altchars=b"-_",
                validate=True,
            )
            value = json.loads(raw.decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("audit cursor is invalid") from exc
        if not isinstance(value, dict) or value.get("v") != _AUDIT_CURSOR_VERSION:
            raise ValueError("audit cursor version is unsupported")
        updated_at = value.get("updated_at")
        audit_id = value.get("audit_id")
        if not isinstance(updated_at, str) or not isinstance(audit_id, str):
            raise TypeError("audit cursor payload is invalid")
        if not audit_id or len(audit_id) > 256 or len(updated_at) > 128:
            raise ValueError("audit cursor payload is invalid")
        return updated_at, audit_id

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
            raise TypeError("run cursor payload is invalid")
        if not run_id or len(run_id) > 512 or len(created_at) > 128:
            raise ValueError("run cursor payload is invalid")
        return created_at, run_id
