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

    Each audit owns one directory with an immutable uploaded PDF plus a mutable
    metadata/event document. Writes use replace-on-success so interrupted writes
    do not leave partial JSON behind.
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
            "events": [],
        }
        with self._lock:
            audit_dir = self._audit_dir(audit_id)
            audit_dir.mkdir(parents=False, exist_ok=False)
            (audit_dir / "paper.pdf").write_bytes(pdf_bytes)
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
        path = self._audit_dir(audit_id) / "paper.pdf"
        if not path.is_file():
            raise FileNotFoundError(f"audit PDF not found: {audit_id}")
        return path

    def append_event(self, event: HarnessEvent) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(event.audit_id)
            record["events"].append(event.to_dict())
            record["updated_at"] = utc_now_iso()
            self._write_record(record)
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
            raise ValueError("audit metadata events must be an array")
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
