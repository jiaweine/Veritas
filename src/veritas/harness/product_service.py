from __future__ import annotations

import json
from collections import deque
from functools import partial
from pathlib import Path
from typing import Any

from .product_store import ProductHarnessStore
from .run_views import project_run_detail
from .service import AuditHarness
from .tools import PaperToolbox

_INTEGRITY_ERRORS = (OSError, ValueError, TypeError, json.JSONDecodeError)


class ProductAuditHarness(AuditHarness):
    """Web/mobile Harness with bounded-memory derived product views.

    The compatibility methods inherited from :class:`AuditHarness` still return
    fully hydrated audit records. Product dashboards instead stream persisted
    events through ``ProductHarnessStore.scan_events`` and retain only the small
    projection each view actually needs.
    """

    def __init__(
        self,
        data_dir: str | Path,
        *,
        toolbox: PaperToolbox | None = None,
    ) -> None:
        super().__init__(data_dir, toolbox=toolbox)
        self.store = ProductHarnessStore(self.store.root)

    def _metadata_audits(self) -> list[dict[str, Any]]:
        return self.store.list_audits(include_events=False)

    def audit_ids(self) -> list[str]:
        """Return valid audit ids without materializing any event history."""

        audit_ids: list[str] = []
        for audit in self._metadata_audits():
            audit_id = str(audit.get("audit_id") or "")
            try:
                self.store.scan_events(audit_id, lambda _event: None)
            except _INTEGRITY_ERRORS:
                continue
            audit_ids.append(audit_id)
        return audit_ids

    def get_audit_metadata(self, audit_id: str) -> dict[str, Any]:
        """Return one integrity-checked audit record without its event list."""

        for audit in self._metadata_audits():
            if str(audit.get("audit_id") or "") != audit_id:
                continue
            self.store.scan_events(audit_id, lambda _event: None)
            return audit
        raise FileNotFoundError(f"audit not found: {audit_id}")

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
            retain = 4 if len(recent_activity) < 8 else 0
            tail: deque[dict[str, Any]] = deque(maxlen=retain)
            try:
                # Scan the complete journal so malformed history still excludes
                # an audit, while retaining at most the tiny activity tail.
                self.store.scan_events(audit_id, tail.append)
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

    def findings(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for audit in self._metadata_audits():
            try:
                self.store.scan_events(str(audit["audit_id"]), lambda _event: None)
            except _INTEGRITY_ERRORS:
                continue
            result = audit.get("latest_result") or {}
            source = result.get("source") or {}
            for index, finding in enumerate(result.get("findings") or []):
                items.append(
                    {
                        "finding_id": f'{audit["audit_id"]}:finding:{index}',
                        "audit_id": audit["audit_id"],
                        "audit_title": audit.get("title"),
                        "title": finding.get("title") or "Finding",
                        "explanation": finding.get("explanation") or "",
                        "severity": finding.get("severity") or "contradiction",
                        "source": finding.get("source") or source,
                        "updated_at": audit.get("updated_at"),
                    }
                )
        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return items

    @staticmethod
    def _collect_run_event(
        runs: list[dict[str, Any]],
        audit: dict[str, Any],
        event: dict[str, Any],
    ) -> None:
        if event.get("kind") != "tool":
            return
        payload = event.get("payload") or {}
        result = payload.get("result") or {}
        phase = payload.get("phase")
        if not result and phase not in {"finish", "error"}:
            return
        runs.append(
            {
                "run_id": payload.get("run_id") or event.get("event_id"),
                "audit_id": audit.get("audit_id"),
                "audit_title": audit.get("title"),
                "tool": payload.get("tool") or "audit.tool",
                "run_kind": payload.get("run_kind") or "audit",
                "task": event.get("title"),
                "phase": phase or "finish",
                "status": event.get("status"),
                "evidence": bool(result.get("source")),
                "coverage": float(result.get("verification_coverage") or 0.0),
                "counts": result.get("counts") or {},
                "duration_ms": payload.get("duration_ms"),
                "artifact_id": payload.get("artifact_id"),
                "parsers": payload.get("parsers") or [],
                "error_type": payload.get("error_type"),
                "created_at": event.get("created_at"),
            }
        )

    def runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for audit in self._metadata_audits():
            try:
                self.store.scan_events(
                    str(audit["audit_id"]),
                    partial(self._collect_run_event, runs, audit),
                )
            except _INTEGRITY_ERRORS:
                # Match list_audits()' historical behavior: a corrupt audit is
                # absent from the derived view rather than partially projected.
                runs[:] = [item for item in runs if item.get("audit_id") != audit.get("audit_id")]
                continue
        runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return runs

    @staticmethod
    def _collect_run_match(
        matched: list[dict[str, Any]],
        run_id: str,
        event: dict[str, Any],
    ) -> None:
        payload = event.get("payload") or {}
        event_run_id = payload.get("run_id") if isinstance(payload, dict) else None
        if event_run_id == run_id or (not event_run_id and event.get("event_id") == run_id):
            matched.append(event)

    def run_detail(self, run_id: str) -> dict[str, Any] | None:
        """Project one correlated run without hydrating unrelated histories."""

        for audit in self._metadata_audits():
            matched: list[dict[str, Any]] = []
            try:
                self.store.scan_events(
                    str(audit["audit_id"]),
                    partial(self._collect_run_match, matched, run_id),
                )
            except _INTEGRITY_ERRORS:
                continue
            if not matched:
                continue
            projected_audit = dict(audit)
            projected_audit["events"] = matched
            return project_run_detail([projected_audit], run_id)
        return None

    @staticmethod
    def _collect_search_match(
        pending: list[dict[str, Any]],
        needle: str,
        remaining: int,
        audit_id: object,
        event: dict[str, Any],
    ) -> None:
        if len(pending) >= remaining:
            return
        haystack = f'{event.get("title", "")} {event.get("detail", "")}'.casefold()
        if needle in haystack:
            pending.append(
                {
                    "kind": "event",
                    "id": event.get("event_id"),
                    "audit_id": audit_id,
                    "title": event.get("title"),
                    "detail": event.get("detail"),
                    "status": event.get("status"),
                }
            )

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        needle = query.strip().casefold()
        if not needle:
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
            pending: list[dict[str, Any]] = []
            if needle in audit_text:
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

            try:
                # Continue scanning after the result cap is reached so corruption
                # later in the visited journal cannot be hidden by an early hit.
                self.store.scan_events(
                    str(audit["audit_id"]),
                    partial(
                        self._collect_search_match,
                        pending,
                        needle,
                        remaining,
                        audit.get("audit_id"),
                    ),
                )
            except _INTEGRITY_ERRORS:
                continue

            results.extend(pending[:remaining])
            if len(results) >= limit:
                return results[:limit]
        return results[:limit]
