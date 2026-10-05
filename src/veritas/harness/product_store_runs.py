from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import HarnessEvent
from .product_store_compact import ProductHarnessStore as _BaseProductHarnessStore

EventVisitor = Callable[[dict[str, Any]], None]
RunSortKey = tuple[str, str]
_RECENT_EVENT_TAIL = 4
_SEARCH_CACHE_MAX_AUDITS = 128
_SEARCH_CACHE_MAX_EVENTS = 20_000
_SEARCH_CACHE_MAX_TEXT_CHARS = 8_000_000
_SEARCH_CACHE_MAX_AUDIT_EVENTS = 10_000
_SEARCH_CACHE_MAX_AUDIT_TEXT_CHARS = 4_000_000


class ProductHarnessStore(_BaseProductHarnessStore):
    """Product store with bounded-cost in-memory product projections.

    The authoritative event journals remain the source of truth. This layer only
    retains bounded projections derived from fully validated journals: terminal
    run rows for Runs, the tiny recent-event tail used by Overview, and an LRU
    cache of event text used by command search. A cold process still validates
    authoritative history before exposing projections; warm requests reuse
    validation watermarks without turning unrelated scans into search-cache
    allocations.
    """

    def __init__(self, root: str | Path) -> None:
        super().__init__(root)
        self._terminal_runs: dict[str, dict[str, Any]] = {}
        self._terminal_sorted_cache: tuple[str, ...] | None = None
        self._recent_event_tails: dict[
            str, tuple[object, tuple[dict[str, Any], ...]]
        ] = {}
        self._search_documents: OrderedDict[
            str, tuple[object, tuple[dict[str, Any], ...]]
        ] = OrderedDict()
        self._search_projection_costs: dict[str, tuple[int, int]] = {}
        self._search_cached_events = 0
        self._search_cached_text_chars = 0

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
        audit_id = event.audit_id
        with self._lock:
            before_fingerprint = self._current_projection_fingerprint_locked(audit_id)
            cached_tail = self._recent_event_tails.get(audit_id)
            tail_was_current = (
                before_fingerprint is not None
                and cached_tail is not None
                and cached_tail[0] == before_fingerprint
            )
            cached_search = self._search_documents.get(audit_id)
            search_was_current = (
                before_fingerprint is not None
                and cached_search is not None
                and cached_search[0] == before_fingerprint
            )

        result = super().append_event(event, hydrate_result=hydrate_result)
        event_dict = event.to_dict()
        summary = self._terminal_summary(audit_id, event_dict)
        with self._lock:
            if summary is not None:
                self._terminal_runs[str(summary["run_id"])] = summary
                self._terminal_sorted_cache = None

            after_fingerprint = self._current_projection_fingerprint_locked(audit_id)
            if tail_was_current and after_fingerprint is not None and cached_tail is not None:
                recent = deque(cached_tail[1], maxlen=_RECENT_EVENT_TAIL)
                recent.append(dict(event_dict))
                self._recent_event_tails[audit_id] = (after_fingerprint, tuple(recent))
            elif cached_tail is not None:
                self._recent_event_tails.pop(audit_id, None)

            if search_was_current and after_fingerprint is not None and cached_search is not None:
                documents = (*cached_search[1], self._search_document(event_dict))
                self._cache_search_projection_locked(
                    audit_id,
                    after_fingerprint,
                    documents,
                )
            elif cached_search is not None:
                self._drop_search_projection_locked(audit_id)
        return result

    def validated_recent_event_tail(self, audit_id: str) -> list[dict[str, Any]]:
        """Return the recent authoritative activity tail for one audit.

        The projection is populated only after a complete journal scan and is
        bound to the exact journal fingerprint that produced it. A later full
        validation of an externally changed journal therefore cannot make an
        older tail look current. Legacy inline-event audits have no fingerprint
        and intentionally stay on the authoritative scan path every time.
        """

        with self._lock:
            cached = self._recent_event_tails.get(audit_id)
            current = self._current_projection_fingerprint_locked(audit_id)
            if cached is not None and current is not None and cached[0] == current:
                return [dict(event) for event in cached[1]]

        tail: deque[dict[str, Any]] = deque(maxlen=_RECENT_EVENT_TAIL)
        self.scan_events(audit_id, lambda event: tail.append(dict(event)))
        projected = tuple(tail)
        with self._lock:
            current = self._current_projection_fingerprint_locked(audit_id)
            if current is None:
                self._recent_event_tails.pop(audit_id, None)
            else:
                self._recent_event_tails[audit_id] = (current, projected)
        return [dict(event) for event in projected]

    def validated_search_matches(
        self,
        audit_id: str,
        needle: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return event substring matches from a validated, bounded search projection.

        Search projections are demand-built only by this method. They are reused
        only while the authoritative journal fingerprint still matches its full
        validation watermark, bounded per audit and globally with LRU eviction,
        and never cached for legacy inline-event audits. Oversized journals keep
        exact search behavior by streaming every query without retaining the
        full searchable history in memory.
        """

        if limit <= 0:
            self.validate_events(audit_id)
            return []

        with self._lock:
            cached = self._search_documents.get(audit_id)
            current = self._current_projection_fingerprint_locked(audit_id)
            if cached is not None and current is not None and cached[0] == current:
                self._search_documents.move_to_end(audit_id)
                return self._matching_search_documents(cached[1], needle, limit=limit)
            if cached is not None:
                self._drop_search_projection_locked(audit_id)

        matched: list[dict[str, Any]] = []
        projected: list[dict[str, Any]] = []
        projected_chars = 0
        cacheable = True

        def capture(event: dict[str, Any]) -> None:
            nonlocal cacheable, projected_chars
            document = self._search_document(event)
            if len(matched) < limit and needle in str(document["haystack"]):
                matched.append(document)
            if not cacheable:
                return
            projected_chars += self._search_document_text_chars(document)
            if (
                len(projected) + 1 > _SEARCH_CACHE_MAX_AUDIT_EVENTS
                or projected_chars > _SEARCH_CACHE_MAX_AUDIT_TEXT_CHARS
            ):
                cacheable = False
                projected.clear()
                return
            projected.append(document)

        self.scan_events(audit_id, capture)

        with self._lock:
            current = self._current_projection_fingerprint_locked(audit_id)
            if cacheable and current is not None:
                self._cache_search_projection_locked(
                    audit_id,
                    current,
                    tuple(projected),
                )
            else:
                self._drop_search_projection_locked(audit_id)
        return [dict(document) for document in matched]

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

    def _current_projection_fingerprint_locked(self, audit_id: str) -> object | None:
        journal = self._event_journal_path(audit_id)
        if not self._event_journal_exists(journal):
            return None
        validated = self._validated_journals.get(audit_id)
        if validated is None:
            return None
        try:
            current = self._path_fingerprint(journal)
        except OSError:
            return None
        return current if validated[0] == current else None

    def _cache_search_projection_locked(
        self,
        audit_id: str,
        fingerprint: object,
        documents: tuple[dict[str, Any], ...],
    ) -> None:
        event_cost = len(documents)
        text_cost = sum(self._search_document_text_chars(document) for document in documents)
        if (
            event_cost > _SEARCH_CACHE_MAX_AUDIT_EVENTS
            or text_cost > _SEARCH_CACHE_MAX_AUDIT_TEXT_CHARS
            or event_cost > _SEARCH_CACHE_MAX_EVENTS
            or text_cost > _SEARCH_CACHE_MAX_TEXT_CHARS
        ):
            self._drop_search_projection_locked(audit_id)
            return

        self._drop_search_projection_locked(audit_id)
        self._search_documents[audit_id] = (fingerprint, documents)
        self._search_projection_costs[audit_id] = (event_cost, text_cost)
        self._search_cached_events += event_cost
        self._search_cached_text_chars += text_cost

        while (
            len(self._search_documents) > _SEARCH_CACHE_MAX_AUDITS
            or self._search_cached_events > _SEARCH_CACHE_MAX_EVENTS
            or self._search_cached_text_chars > _SEARCH_CACHE_MAX_TEXT_CHARS
        ):
            oldest_audit_id = next(iter(self._search_documents))
            self._drop_search_projection_locked(oldest_audit_id)

    def _drop_search_projection_locked(self, audit_id: str) -> None:
        self._search_documents.pop(audit_id, None)
        cost = self._search_projection_costs.pop(audit_id, None)
        if cost is not None:
            self._search_cached_events -= cost[0]
            self._search_cached_text_chars -= cost[1]

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
    def _search_document(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": event.get("event_id"),
            "title": event.get("title"),
            "detail": event.get("detail"),
            "status": event.get("status"),
            "haystack": f"{event.get('title', '')} {event.get('detail', '')}".casefold(),
        }

    @staticmethod
    def _search_document_text_chars(document: dict[str, Any]) -> int:
        return sum(
            len(str(document.get(key) or ""))
            for key in ("event_id", "title", "detail", "status", "haystack")
        )

    @staticmethod
    def _matching_search_documents(
        documents: tuple[dict[str, Any], ...],
        needle: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        matched: list[dict[str, Any]] = []
        for document in documents:
            if needle not in str(document.get("haystack") or ""):
                continue
            matched.append(dict(document))
            if len(matched) >= limit:
                break
        return matched

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
