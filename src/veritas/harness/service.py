from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from .models import HarnessEvent
from .planner import help_text, parse_command
from .store import HarnessStore
from .tools import PaperToolbox


class AuditHarness:
    """Conversation-oriented orchestration around deterministic Veritas tools."""

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
            tool_status = "success" if result["status"] == "verified" else (
                "danger" if result["status"] == "contradiction" else "review"
            )
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
        except Exception as exc:
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
