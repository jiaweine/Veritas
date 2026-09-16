from __future__ import annotations

import json
import threading
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import HarnessEvent, utc_now_iso


class HarnessStore:
    """Small local-first audit store used by the web harness.

    Each audit owns one directory with an immutable uploaded PDF, optional
    immutable reproduction attachments, and a mutable metadata/event document.
    Writes use replace-on-success so interrupted metadata writes do not leave
    partial JSON behind.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create_audit(
        self,
        *,
        title: str,
        filename: str,
        pdf_bytes: bytes,
        paper_summary: dict[str, Any],
    ) -> dict[str, Any]:
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("uploaded artifact must be a PDF")
        clean_title = title.strip() or Path(filename).stem or "Untitled paper"
        audit_id = f"audit_{uuid4().hex[:12]}"
        now = utc_now_iso()
        record = {
            "audit_id": audit_id,
            "title": clean_title,
            "filename": Path(filename).name or "paper.pdf",
            "status": "ready",
            "created_at": now,
            "updated_at": now,
            "artifact_sha256": sha256(pdf_bytes).hexdigest(),
            "paper_summary": paper_summary,
            "latest_result": None,
            "attachments": [],
            "events": [],
        }
        with self._lock:
            audit_dir = self._audit_dir(audit_id)
            audit_dir.mkdir(parents=False, exist_ok=False)
            paper = audit_dir / "paper.pdf"
            paper.write_bytes(pdf_bytes)
            try:
                paper.chmod(0o444)
            except OSError:
                pass
            self._write_record(record)
        return record

    def list_audits(self) -> list[dict[str, Any]]:
        with self._lock:
            records = []
            for path in self.root.glob("audit_*/audit.json"):
                try:
                    records.append(self._read_record(path.parent.name))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue
        records.sort(key=lambda item: str(item["updated_at"]), reverse=True)
        return records

    def get_audit(self, audit_id: str) -> dict[str, Any]:
        with self._lock:
            return self._read_record(audit_id)

    def get_pdf_path(self, audit_id: str) -> Path:
        with self._lock:
            record = self._read_record(audit_id)
            path = self._audit_dir(audit_id) / "paper.pdf"
            if not path.is_file():
                raise FileNotFoundError(f"audit PDF not found: {audit_id}")
            if sha256(path.read_bytes()).hexdigest() != record.get("artifact_sha256"):
                raise ValueError(f"audit PDF hash mismatch: {audit_id}")
            return path

    def add_attachment(
        self,
        audit_id: str,
        *,
        filename: str,
        payload: bytes,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, bytes):
            raise TypeError("attachment payload must be bytes")
        if not payload:
            raise ValueError("attachment must not be empty")
        clean_name = self._clean_attachment_name(filename)
        attachment_id = f"att_{uuid4().hex[:12]}"
        now = utc_now_iso()
        digest = sha256(payload).hexdigest()
        metadata = {
            "attachment_id": attachment_id,
            "filename": clean_name,
            "sha256": digest,
            "size_bytes": len(payload),
            "media_type": (media_type or "application/octet-stream").strip()
            or "application/octet-stream",
            "created_at": now,
        }

        with self._lock:
            record = self._read_record(audit_id)
            attachment_dir = self._audit_dir(audit_id) / "attachments" / attachment_id
            attachment_dir.mkdir(parents=True, exist_ok=False)
            destination = attachment_dir / clean_name
            destination.write_bytes(payload)
            try:
                destination.chmod(0o444)
            except OSError:
                pass
            record["attachments"].append(metadata)
            record["updated_at"] = now
            self._write_record(record)
        return dict(metadata)

    def list_attachments(self, audit_id: str) -> list[dict[str, Any]]:
        with self._lock:
            record = self._read_record(audit_id)
            return [dict(item) for item in record["attachments"]]

    def get_attachment_path(self, audit_id: str, attachment_id: str) -> Path:
        if not attachment_id.startswith("att_") or not attachment_id[4:].isalnum():
            raise ValueError("invalid attachment id")
        with self._lock:
            record = self._read_record(audit_id)
            metadata = next(
                (
                    item
                    for item in record["attachments"]
                    if item.get("attachment_id") == attachment_id
                ),
                None,
            )
            if metadata is None:
                raise FileNotFoundError(f"attachment not found: {attachment_id}")
            filename = self._clean_attachment_name(str(metadata.get("filename") or ""))
            path = self._audit_dir(audit_id) / "attachments" / attachment_id / filename
            if not path.is_file():
                raise FileNotFoundError(f"attachment payload not found: {attachment_id}")
            if sha256(path.read_bytes()).hexdigest() != metadata.get("sha256"):
                raise ValueError(f"attachment hash mismatch: {attachment_id}")
            return path

    def append_event(self, event: HarnessEvent) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(event.audit_id)
            record["events"].append(event.to_dict())
            record["updated_at"] = utc_now_iso()
            self._write_record(record)

        # Observability is best-effort and happens only after the local append is
        # durable. Exporting must never be able to change the audit result.
        try:
            from .telemetry import export_terminal_run

            export_terminal_run(record, event)
        except (ImportError, RuntimeError, TypeError, ValueError):
            pass
        return record

    def set_status(self, audit_id: str, status: str) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(audit_id)
            record["status"] = status
            record["updated_at"] = utc_now_iso()
            self._write_record(record)
            return record

    def set_latest_result(self, audit_id: str, result: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(audit_id)
            record["latest_result"] = result
            record["status"] = "ready"
            record["updated_at"] = utc_now_iso()
            self._write_record(record)
            return record

    def _audit_dir(self, audit_id: str) -> Path:
        if not audit_id.startswith("audit_") or not audit_id[6:].isalnum():
            raise ValueError("invalid audit id")
        return self.root / audit_id

    def _read_record(self, audit_id: str) -> dict[str, Any]:
        path = self._audit_dir(audit_id) / "audit.json"
        if not path.is_file():
            raise FileNotFoundError(f"audit not found: {audit_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("audit_id") != audit_id:
            raise ValueError("audit metadata is invalid")
        if not isinstance(value.get("events"), list):
            raise TypeError("audit metadata events must be an array")
        attachments = value.setdefault("attachments", [])
        if not isinstance(attachments, list):
            raise TypeError("audit metadata attachments must be an array")
        if any(not isinstance(item, dict) for item in attachments):
            raise TypeError("audit metadata attachment entries must be objects")
        return value

    def _write_record(self, record: dict[str, Any]) -> None:
        audit_id = str(record["audit_id"])
        audit_dir = self._audit_dir(audit_id)
        audit_dir.mkdir(parents=True, exist_ok=True)
        destination = audit_dir / "audit.json"
        temporary = audit_dir / "audit.json.tmp"
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    @staticmethod
    def _clean_attachment_name(filename: str) -> str:
        if not isinstance(filename, str) or "\x00" in filename:
            raise ValueError("attachment filename is invalid")
        clean = Path(filename.replace("\\", "/")).name.strip()
        if not clean or clean in {".", ".."}:
            raise ValueError("attachment filename is required")
        if len(clean) > 240:
            raise ValueError("attachment filename is too long")
        return clean
