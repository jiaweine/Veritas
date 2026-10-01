from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import HarnessEvent
from .product_store_compact import ProductHarnessStore as _BaseProductHarnessStore

EventVisitor = Callable[[dict[str, Any]], None]
RunSortKey = tuple[str, str]


class ProductHarnessStore(_BaseProductHarnessStore):
    """Product store with a bounded-cost in-memory terminal-run projection.

    The authoritative event journals remain the source of truth. This layer only
    retains the compact terminal row that the Runs product surface already
    derives from a fully validated journal. A cold process still validates each
    audit before exposing rows; warm requests reuse the validation watermarks and
    avoid reparsing unrelated event history.
    """

    def __init__(self, root: str | Path) -> None:
        super().__init__(root)
        self._terminal_runs: dict[str, dict[str, Any]] = {}
        self._terminal_sorted_cache: tuple[str, ...] | None = None

    def scan_events(self, audit_id: str, visitor: EventVisitor) -> int:
        projected: dict[str, dict[str, Any]] = {}

        def capture(event: dict[str, Any]) -> None:
            visitor(event)
            summary = self._terminal_summary(audit_id, event)
            if summary is not None:
                projected[str(summary["run_id"])] = summary

        count = super().scan_events(audit_id, capture)
        with self._lock:
            stale = [
                run_id
                for run_id, item in self._terminal_runs.items()
                if str(item.get("audit_id") or "") == audit_id
            ]
            changed = bool(stale) or bool(projected)
            for run_id in stale:
                self._terminal_runs.pop(run_id, None)
            self._terminal_runs.update(projected)
            if changed:
                self._terminal_sorted_cache = None
        return count

    def append_event(
        self,
        event: HarnessEvent,
        *,
        hydrate_result: bool = False,
    ) -> dict[str, Any]:
        result = super().append_event(event, hydrate_result=hydrate_result)
        summary = self._terminal_summary(event.audit_id, event.to_dict())
        if summary is not None:
            with self._lock:
                self._terminal_runs[str(summary["run_id"])] = summary
                self._terminal_sorted_cache = None
        return result

    def terminal_runs(self, valid_audit_ids: set[str]) -> list[dict[str, Any]]:
        """Return terminal run rows only for journals validated by the caller."""

        with self._lock:
            current_audits = self._current_valid_audits_locked(valid_audit_ids)
            return [
                dict(self._terminal_runs[run_id])
                for run_id in self._sorted_terminal_run_ids_locked()
                if str(self._terminal_runs[run_id].get("audit_id") or "") in current_audits
            ]

    def terminal_run_page(
        self,
        valid_audit_ids: set[str],
        *,
        limit: int,
        after: RunSortKey | None = None,
    ) -> tuple[list[dict[str, Any]], bool, RunSortKey | None]:
        if limit < 1:
            raise ValueError("run page limit must be positive")
        with self._lock:
            current_audits = self._current_valid_audits_locked(valid_audit_ids)
            selected: list[dict[str, Any]] = []
            for run_id in self._sorted_terminal_run_ids_locked():
                item = self._terminal_runs[run_id]
                if str(item.get("audit_id") or "") not in current_audits:
                    continue
                key = self._summary_sort_key(item)
                if after is not None and key >= after:
                    continue
                selected.append(dict(item))
                if len(selected) > limit:
                    break

        has_more = len(selected) > limit
        page = selected[:limit]
        next_key = self._summary_sort_key(page[-1]) if has_more and page else None
        return page, has_more, next_key

    def _current_valid_audits_locked(self, valid_audit_ids: set[str]) -> set[str]:
        current: set[str] = set()
        for audit_id in valid_audit_ids:
            journal = self._event_journal_path(audit_id)
            if not self._event_journal_exists(journal):
                # Legacy inline-event audits are reparsed by validate_events on
                # every request because they have no journal watermark.
                current.add(audit_id)
                continue
            cached = self._validated_journals.get(audit_id)
            if cached is None:
                continue
            try:
                fingerprint = self._path_fingerprint(journal)
            except OSError:
                continue
            if cached[0] == fingerprint:
                current.add(audit_id)
        return current

    def _sorted_terminal_run_ids_locked(self) -> tuple[str, ...]:
        if self._terminal_sorted_cache is None:
            self._terminal_sorted_cache = tuple(
                sorted(
                    self._terminal_runs,
                    key=lambda run_id: self._summary_sort_key(self._terminal_runs[run_id]),
                    reverse=True,
                )
            )
        return self._terminal_sorted_cache

    @staticmethod
    def _summary_sort_key(item: dict[str, Any]) -> RunSortKey:
        return str(item.get("created_at") or ""), str(item.get("run_id") or "")

    @staticmethod
    def _terminal_summary(audit_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        if event.get("kind") != "tool":
            return None
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return None
        result = payload.get("result")
        result_dict = result if isinstance(result, dict) else {}
        phase = str(payload.get("phase") or "")
        if not result_dict and phase not in {"finish", "error", "cancelled"}:
            return None
        run_id = payload.get("run_id") or event.get("event_id")
        clean_run_id = str(run_id or "").strip()
        if not clean_run_id:
            return None
        counts = result_dict.get("counts")
        parsers = payload.get("parsers")
        return {
            "run_id": clean_run_id,
            "audit_id": audit_id,
            "tool": payload.get("tool") or "audit.tool",
            "run_kind": payload.get("run_kind") or "audit",
            "task": event.get("title"),
            "phase": phase or "finish",
            "status": event.get("status"),
            "evidence": bool(result_dict.get("source")),
            "coverage": float(result_dict.get("verification_coverage") or 0.0),
            "counts": dict(counts) if isinstance(counts, dict) else {},
            "duration_ms": payload.get("duration_ms"),
            "artifact_id": payload.get("artifact_id"),
            "parsers": list(parsers) if isinstance(parsers, list) else [],
            "error_type": payload.get("error_type"),
            "created_at": event.get("created_at"),
        }
