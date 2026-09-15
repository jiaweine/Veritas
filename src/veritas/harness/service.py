from __future__ import annotations

from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from typing import Any

from .models import HarnessEvent
from .planner import help_text, parse_command
from .store import HarnessStore
from .tools import PaperToolbox


class AuditHarness:
    """Conversation-oriented orchestration around deterministic Veritas tools.

    The product API intentionally stays thin: the existing evidence and detector
    code remains authoritative, while this class exposes derived views for web
    and mobile clients without duplicating audit logic in the UI.
    """

    def __init__(
        self,
        data_dir: str | Path,
        *,
        toolbox: PaperToolbox | None = None,
    ) -> None:
        self.store = HarnessStore(data_dir)
        self.toolbox = toolbox or PaperToolbox()
        self._snapshot_cache: dict[str, tuple[object, ...]] = {}

    def create_audit(
        self,
        *,
        title: str,
        filename: str,
        pdf_bytes: bytes,
    ) -> dict[str, Any]:
        artifact_id = f"paper-{sha256(pdf_bytes).hexdigest()[:12]}"
        snapshots = self.toolbox.parse(pdf_bytes, artifact_id=artifact_id)
        summary = self.toolbox.describe(
            pdf_bytes,
            artifact_id=artifact_id,
            snapshots=snapshots,
        )
        record = self.store.create_audit(
            title=title,
            filename=filename,
            pdf_bytes=pdf_bytes,
            paper_summary=summary,
        )
        self._snapshot_cache[str(record["audit_id"])] = snapshots

        event = HarnessEvent(
            audit_id=str(record["audit_id"]),
            kind="paper",
            title="Paper parsed",
            detail=(
                f'{summary["pages"]} pages · {summary["tables_detected"]} tables · '
                f'{summary["words"]:,} words'
            ),
            status="success",
            payload={"paper_summary": summary},
        )
        self.store.append_event(event)
        return self.store.get_audit(str(record["audit_id"]))

    def list_audits(self) -> list[dict[str, Any]]:
        return self.store.list_audits()

    def get_audit(self, audit_id: str) -> dict[str, Any]:
        return self.store.get_audit(audit_id)

    def paper_path(self, audit_id: str) -> Path:
        return self.store.get_pdf_path(audit_id)

    def overview(self) -> dict[str, Any]:
        audits = self.store.list_audits()
        total_pages = 0
        running = 0
        verified = 0
        needs_review = 0
        contradictions = 0
        coverage_values: list[float] = []
        recent_activity: list[dict[str, Any]] = []
        coverage_series: list[dict[str, Any]] = []

        for audit in audits:
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

            for event in reversed((audit.get("events") or [])[-4:]):
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
            "audits_total": len(audits),
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
            "updated_at": audits[0].get("updated_at") if audits else None,
        }

    def findings(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for audit in self.store.list_audits():
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
        for audit in self.store.list_audits():
            for event in audit.get("events") or []:
                if event.get("kind") != "tool":
                    continue
                payload = event.get("payload") or {}
                result = payload.get("result") or {}
                runs.append(
                    {
                        "run_id": event.get("event_id"),
                        "audit_id": audit.get("audit_id"),
                        "audit_title": audit.get("title"),
                        "tool": payload.get("tool") or "audit.tool",
                        "task": event.get("title"),
                        "status": event.get("status"),
                        "evidence": bool(result.get("source")),
                        "coverage": float(result.get("verification_coverage") or 0.0),
                        "counts": result.get("counts") or {},
                        "created_at": event.get("created_at"),
                    }
                )
        runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return runs

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        needle = query.strip().casefold()
        if not needle:
            return []
        results: list[dict[str, Any]] = []
        for audit in self.store.list_audits():
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
            for event in audit.get("events") or []:
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
        return results[:limit]

    @staticmethod
    def capabilities() -> dict[str, Any]:
        return {
            "api_version": "v1",
            "streaming": "ndjson",
            "max_upload_bytes": 80 * 1024 * 1024,
            "clients": ["web", "pwa", "expo"],
            "features": {
                "pdf_upload": True,
                "evidence_inspector": True,
                "findings": True,
                "runs": True,
                "command_palette": True,
                "offline_shell": True,
            },
        }

    def stream_message(self, audit_id: str, message: str) -> Iterator[dict[str, Any]]:
        record = self.store.get_audit(audit_id)
        user_event = HarnessEvent(
            audit_id=audit_id,
            kind="user_message",
            title=message.strip(),
            status="info",
        )
        self.store.append_event(user_event)
        yield user_event.to_dict()

        try:
            command = parse_command(message)
        except ValueError as exc:
            event = HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title="I need a little more structure for that audit.",
                detail=f"{exc}. {help_text()}",
                status="review",
            )
            self.store.append_event(event)
            yield event.to_dict()
            return

        if command.action == "help" or command.action == "chat":
            event = HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title="Ready to audit this paper.",
                detail=help_text(),
                status="info",
                payload={"commands": ["/inspect", '/audit row="Treatment" table=2 page=1']},
            )
            self.store.append_event(event)
            yield event.to_dict()
            return

        if command.action == "inspect":
            summary = record["paper_summary"]
            event = HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title="Paper structure",
                detail=(
                    f'{summary["pages"]} pages, {summary["tables_detected"]} detected tables. '
                    "Select a table in the Evidence Inspector or run an audit on a row label."
                ),
                status="success",
                payload={"paper_summary": summary},
            )
            self.store.append_event(event)
            yield event.to_dict()
            return

        self.store.set_status(audit_id, "running")
        start = HarnessEvent(
            audit_id=audit_id,
            kind="tool",
            title="Regression audit",
            detail=(
                f'Locating “{command.row_label}”'
                + (f" in {command.table_label}" if command.table_label else "")
                + (f" on page {command.expected_page}" if command.expected_page else "")
            ),
            status="running",
            payload={
                "tool": "audit.regression",
                "row_label": command.row_label,
                "table_label": command.table_label,
                "expected_page": command.expected_page,
            },
        )
        self.store.append_event(start)
        yield start.to_dict()

        try:
            pdf_bytes = self.store.get_pdf_path(audit_id).read_bytes()
            snapshots = self._snapshot_cache.get(audit_id)
            if snapshots is None:
                artifact_id = str(record["paper_summary"]["artifact_id"])
                snapshots = self.toolbox.parse(pdf_bytes, artifact_id=artifact_id)
                self._snapshot_cache[audit_id] = snapshots

            result = self.toolbox.audit_regression(
                pdf_bytes,
                artifact_id=str(record["paper_summary"]["artifact_id"]),
                row_label=str(command.row_label),
                table_label=command.table_label,
                expected_page=command.expected_page,
                snapshots=snapshots,
            )
            self.store.set_latest_result(audit_id, result)

            counts = result.get("counts", {})
            if result["status"] == "verified":
                tool_status = "success"
            elif result["status"] == "contradiction":
                tool_status = "danger"
            else:
                tool_status = "review"
            detail = self._result_detail(result)
            finished = HarnessEvent(
                audit_id=audit_id,
                kind="tool",
                title="Regression consistency checked",
                detail=detail,
                status=tool_status,
                payload={"tool": "audit.regression", "result": result},
            )
            self.store.append_event(finished)
            yield finished.to_dict()

            for finding in result.get("findings", []):
                finding_event = HarnessEvent(
                    audit_id=audit_id,
                    kind="finding",
                    title=str(finding.get("title", "Finding")),
                    detail=str(finding.get("explanation", "")),
                    status="danger",
                    payload={"finding": finding, "source": result.get("source", {})},
                )
                self.store.append_event(finding_event)
                yield finding_event.to_dict()

            final = HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title=self._result_title(result),
                detail=self._assistant_detail(result, counts),
                status=tool_status,
                payload={"result": result},
            )
            self.store.append_event(final)
            yield final.to_dict()
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
            self.store.set_status(audit_id, "error")
            event = HarnessEvent(
                audit_id=audit_id,
                kind="assistant_message",
                title="Audit could not complete",
                detail=f"{type(exc).__name__}: {exc}",
                status="danger",
                payload={"error_type": type(exc).__name__},
            )
            self.store.append_event(event)
            yield event.to_dict()

    @staticmethod
    def _result_detail(result: dict[str, Any]) -> str:
        if result["status"] == "review_required" and result.get("review_reasons"):
            return " · ".join(str(item) for item in result["review_reasons"])
        counts = result.get("counts", {})
        return (
            f'{counts.get("verified", 0)} verified · '
            f'{counts.get("needs_review", 0)} need review · '
            f'{counts.get("contradictions", 0)} contradictions'
        )

    @staticmethod
    def _result_title(result: dict[str, Any]) -> str:
        status = result["status"]
        if status == "contradiction":
            return "I found a reporting contradiction."
        if status == "review_required":
            return "This row needs review."
        return "The reported values are internally consistent."

    @staticmethod
    def _assistant_detail(result: dict[str, Any], counts: dict[str, Any]) -> str:
        source = result.get("source", {})
        location = []
        if source.get("table"):
            location.append(str(source["table"]))
        if source.get("page"):
            location.append(f'page {source["page"]}')
        where = " · ".join(location) or "the located source"
        return (
            f'Checked {where}. Verification coverage: '
            f'{float(result.get("verification_coverage", 0.0)):.0%}. '
            f'{counts.get("verified", 0)} checks passed, '
            f'{counts.get("needs_review", 0)} need review, '
            f'{counts.get("contradictions", 0)} contradictions.'
        )
