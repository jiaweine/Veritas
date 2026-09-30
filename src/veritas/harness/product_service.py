from __future__ import annotations

import json
from typing import Any

from .service import AuditHarness

_INTEGRITY_ERRORS = (OSError, ValueError, TypeError, json.JSONDecodeError)


class ProductAuditHarness(AuditHarness):
    """Web/mobile Harness with bounded-memory derived product views.

    The compatibility methods inherited from :class:`AuditHarness` still return
    fully hydrated audit records. Product dashboards do not need every event from
    every audit at once, so these projections keep audit metadata separate from
    event-history reads and validate journals one audit at a time.
    """

    def _metadata_audits(self) -> list[dict[str, Any]]:
        return self.store.list_audits(include_events=False)

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
                # Preserve the historical integrity behavior of list_audits():
                # malformed journals are omitted from derived views. Retain at
                # most four events only while the activity feed still needs them;
                # otherwise validate the complete journal without retaining it.
                tail = self.store.get_events(
                    audit_id,
                    limit=4 if len(recent_activity) < 8 else 0,
                )
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
                self.store.get_events(str(audit["audit_id"]), limit=0)
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

    def runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for audit in self._metadata_audits():
            try:
                events = self.store.get_events(str(audit["audit_id"]))
            except _INTEGRITY_ERRORS:
                continue
            for event in events:
                if event.get("kind") != "tool":
                    continue
                payload = event.get("payload") or {}
                result = payload.get("result") or {}
                phase = payload.get("phase")
                if not result and phase not in {"finish", "error"}:
                    continue
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
            # Drop the per-audit history before opening the next journal. This is
            # deliberate even though CPython would release it on reassignment.
            del events
        runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return runs

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        needle = query.strip().casefold()
        if not needle:
            return []
        results: list[dict[str, Any]] = []
        for audit in self._metadata_audits():
            audit_id = str(audit.get("audit_id") or "")
            try:
                events = self.store.get_events(audit_id)
            except _INTEGRITY_ERRORS:
                continue

            audit_text = " ".join(
                str(value or "")
                for value in (audit.get("title"), audit.get("filename"), audit.get("audit_id"))
            ).casefold()
            if needle in audit_text:
                results.append(
                    {
                        "kind": "audit",
                        "id": audit.get("audit_id"),
                        "audit_id": audit.get("audit_id"),
                        "title": audit.get("title"),
                        "detail": audit.get("filename"),
                        "status": audit.get("status"),
                    }
                )

            for event in events:
                haystack = f'{event.get("title", "")} {event.get("detail", "")}'.casefold()
                if needle in haystack:
                    results.append(
                        {
                            "kind": "event",
                            "id": event.get("event_id"),
                            "audit_id": audit.get("audit_id"),
                            "title": event.get("title"),
                            "detail": event.get("detail"),
                            "status": event.get("status"),
                        }
                    )
                if len(results) >= limit:
                    return results[:limit]
            del events
        return results[:limit]
