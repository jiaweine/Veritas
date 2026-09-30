from __future__ import annotations

import json
import os
import threading
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import HarnessEvent, utc_now_iso

MAX_AUDIT_NOTES_CHARS = 50_000
EVENT_JOURNAL_FILENAME = "events.ndjson"
EVENT_JOURNAL_SCHEMA_VERSION = "1"

_ROOT_LOCKS_GUARD = threading.Lock()
_ROOT_LOCKS: dict[Path, threading.RLock] = {}


def _shared_root_lock(root: Path) -> threading.RLock:
    """Return one process-wide lock for every store instance sharing a root.

    A single FastAPI process can create more than one ``HarnessStore`` for the
    same data directory (tests, reloads, embedded apps). Instance-local locks
    let those stores race on the same ``audit.json`` temporary file and can
    lose read-modify-write updates. Sharing the lock by resolved root keeps
    same-process access serial without changing the on-disk schema.
    """

    with _ROOT_LOCKS_GUARD:
        lock = _ROOT_LOCKS.get(root)
        if lock is None:
            lock = threading.RLock()
            _ROOT_LOCKS[root] = lock
        return lock


class HarnessStore:
    """Small local-first audit store used by the web harness.

    Each audit owns one directory with an immutable uploaded PDF, optional
    immutable reproduction attachments, compact mutable metadata, and an
    append-only event journal. Metadata writes use replace-on-success while
    events use durable NDJSON appends so a long replication trace does not
    rewrite the entire history for every streamed update.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = _shared_root_lock(self.root)

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
            "notes": "",
            "notes_updated_at": None,
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
            record = self._read_record(audit_id, include_events=False)
            path = self._audit_dir(audit_id) / "paper.pdf"
            if not path.is_file():
                raise FileNotFoundError(f"audit PDF not found: {audit_id}")
            if self._file_sha256(path) != record.get("artifact_sha256"):
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
            record = self._read_record(audit_id, include_events=False)
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
            record = self._read_record(audit_id, include_events=False)
            return [dict(item) for item in record["attachments"]]

    def get_attachment_path(self, audit_id: str, attachment_id: str) -> Path:
        if not attachment_id.startswith("att_") or not attachment_id[4:].isalnum():
            raise ValueError("invalid attachment id")
        with self._lock:
            record = self._read_record(audit_id, include_events=False)
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
            if self._file_sha256(path) != metadata.get("sha256"):
                raise ValueError(f"attachment hash mismatch: {attachment_id}")
            return path

    def append_event(self, event: HarnessEvent) -> dict[str, Any]:
        with self._lock:
            audit_id = event.audit_id
            journal = self._event_journal_path(audit_id)
            if journal.exists():
                record = self._read_record(audit_id, include_events=False)
            else:
                # Legacy audit.json files stored the complete event history inline.
                # The first append migrates that history atomically into NDJSON.
                record = self._read_record(audit_id)
                self._ensure_event_journal(record)

            event_dict = event.to_dict()
            self._append_journal_event(journal, event_dict)
            record["updated_at"] = utc_now_iso()
            self._write_record(record)

            # Preserve the historical append_event return contract without making
            # the durable metadata document grow with the event history.
            result = self._read_record(audit_id)

        # Observability is best-effort and happens only after the local append is
        # durable. Exporting must never be able to change the audit result.
        try:
            from .telemetry import export_terminal_run

            export_terminal_run(result, event)
        except (ImportError, RuntimeError, TypeError, ValueError):
            pass
        return result

    def set_status(self, audit_id: str, status: str) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(audit_id, include_events=False)
            record["status"] = status
            record["updated_at"] = utc_now_iso()
            self._write_record(record)
            return self._read_record(audit_id)

    def set_latest_result(self, audit_id: str, result: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(audit_id, include_events=False)
            record["latest_result"] = result
            record["status"] = "ready"
            record["updated_at"] = utc_now_iso()
            self._write_record(record)
            return self._read_record(audit_id)

    def set_notes(self, audit_id: str, notes: str) -> dict[str, Any]:
        if not isinstance(notes, str):
            raise TypeError("audit notes must be text")
        if len(notes) > MAX_AUDIT_NOTES_CHARS:
            raise ValueError(
                f"audit notes exceed the {MAX_AUDIT_NOTES_CHARS:,} character limit"
            )
        with self._lock:
            record = self._read_record(audit_id, include_events=False)
            now = utc_now_iso()
            record["notes"] = notes
            record["notes_updated_at"] = now
            record["updated_at"] = now
            self._write_record(record)
            return self._read_record(audit_id)

    def _audit_dir(self, audit_id: str) -> Path:
        if not audit_id.startswith("audit_") or not audit_id[6:].isalnum():
            raise ValueError("invalid audit id")
        return self.root / audit_id

    def _event_journal_path(self, audit_id: str) -> Path:
        return self._audit_dir(audit_id) / EVENT_JOURNAL_FILENAME

    def _read_record(self, audit_id: str, *, include_events: bool = True) -> dict[str, Any]:
        path = self._audit_dir(audit_id) / "audit.json"
        if not path.is_file():
            raise FileNotFoundError(f"audit not found: {audit_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("audit_id") != audit_id:
            raise ValueError("audit metadata is invalid")
        embedded_events = value.get("events")
        if not isinstance(embedded_events, list):
            raise TypeError("audit metadata events must be an array")
        if any(not isinstance(item, dict) for item in embedded_events):
            raise TypeError("audit metadata event entries must be objects")

        journal = self._event_journal_path(audit_id)
        if journal.exists():
            marker = value.setdefault(
                "event_journal",
                {"schema_version": EVENT_JOURNAL_SCHEMA_VERSION, "path": EVENT_JOURNAL_FILENAME},
            )
            if not isinstance(marker, dict):
                raise TypeError("audit metadata event_journal must be an object")
            if marker.get("schema_version") not in {None, EVENT_JOURNAL_SCHEMA_VERSION}:
                raise ValueError("unsupported audit event journal schema")
            if marker.get("path") not in {None, EVENT_JOURNAL_FILENAME}:
                raise ValueError("audit event journal path is invalid")
            value["events"] = self._read_event_journal(journal) if include_events else []
        elif not include_events:
            value["events"] = []

        attachments = value.setdefault("attachments", [])
        if not isinstance(attachments, list):
            raise TypeError("audit metadata attachments must be an array")
        if any(not isinstance(item, dict) for item in attachments):
            raise TypeError("audit metadata attachment entries must be objects")
        notes = value.setdefault("notes", "")
        if not isinstance(notes, str):
            raise TypeError("audit metadata notes must be text")
        notes_updated_at = value.setdefault("notes_updated_at", None)
        if notes_updated_at is not None and not isinstance(notes_updated_at, str):
            raise TypeError("audit metadata notes_updated_at must be text or null")
        return value

    def _ensure_event_journal(self, record: dict[str, Any]) -> Path:
        audit_id = str(record["audit_id"])
        journal = self._event_journal_path(audit_id)
        if journal.exists():
            return journal

        events = record.get("events")
        if not isinstance(events, list) or any(not isinstance(item, dict) for item in events):
            raise TypeError("audit metadata events must be an array of objects")

        audit_dir = self._audit_dir(audit_id)
        temporary = audit_dir / f".{EVENT_JOURNAL_FILENAME}.{uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                for item in events:
                    handle.write(self._event_line(item))
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(journal)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

        record["event_journal"] = {
            "schema_version": EVENT_JOURNAL_SCHEMA_VERSION,
            "path": EVENT_JOURNAL_FILENAME,
        }
        self._write_record(record)
        return journal

    def _append_journal_event(self, journal: Path, event: dict[str, Any]) -> None:
        rendered = self._event_line(event)
        with journal.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _event_line(event: dict[str, Any]) -> str:
        return json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"

    @staticmethod
    def _read_event_journal(path: Path) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ValueError(f"audit event journal contains a blank line at {line_number}")
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"audit event journal contains invalid JSON at line {line_number}"
                    ) from exc
                if not isinstance(event, dict):
                    raise TypeError(
                        f"audit event journal entry at line {line_number} must be an object"
                    )
                events.append(event)
        return events

    def _write_record(self, record: dict[str, Any]) -> None:
        audit_id = str(record["audit_id"])
        audit_dir = self._audit_dir(audit_id)
        audit_dir.mkdir(parents=True, exist_ok=True)
        destination = audit_dir / "audit.json"
        temporary = audit_dir / f".audit.json.{uuid4().hex}.tmp"

        stored = dict(record)
        journal = self._event_journal_path(audit_id)
        if journal.exists():
            stored["events"] = []
            stored["event_journal"] = {
                "schema_version": EVENT_JOURNAL_SCHEMA_VERSION,
                "path": EVENT_JOURNAL_FILENAME,
            }
        rendered = json.dumps(stored, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

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
