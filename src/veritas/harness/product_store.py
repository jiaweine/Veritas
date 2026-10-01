from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import HarnessEvent
from .store import _JOURNAL_READ_FLAGS, HarnessStore

EventVisitor = Callable[[dict[str, Any]], None]
_SCAN_CHUNK_BYTES = 64 * 1024
_RUN_INDEX_FILENAME = ".run-index.ndjson"
_RUN_INDEX_SCHEMA_VERSION = "1"
_MAX_RUN_INDEX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class _JournalFingerprint:
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass
class _RunRange:
    audit_id: str
    start: int
    end: int
    complete: bool = False


class ProductHarnessStore(HarnessStore):
    """HarnessStore variant with integrity-preserving streaming event scans.

    Product projections often need to inspect every persisted event but retain
    only a tiny derived result. ``HarnessStore.get_events()`` intentionally
    returns a list for compatibility; this scanner keeps that contract intact
    while giving the web/mobile runtime a zero-history-retention path.

    Journal scans snapshot the authoritative file length while holding the
    shared root lock, then release that lock before parsing the already-open file
    descriptor. Concurrent appends can therefore continue while a dashboard
    view scans an older, complete prefix of the journal.

    A compact auxiliary run-range index accelerates repeated run lookups. The
    index is never authoritative: every indexed read first requires a current
    full-journal validation watermark, and stale/corrupt index entries fall back
    to authoritative journal scanning.
    """

    def __init__(self, root: str | Path) -> None:
        super().__init__(root)
        self._validated_journals: dict[str, tuple[_JournalFingerprint, int]] = {}
        self._run_ranges: dict[str, _RunRange] = {}
        self._run_index_loaded = False
        self._run_index_fingerprint: _JournalFingerprint | None = None

    def scan_events(self, audit_id: str, visitor: EventVisitor) -> int:
        if not callable(visitor):
            raise TypeError("event visitor must be callable")

        inline_events: list[dict[str, Any]] | None = None
        fd = -1
        snapshot_size = 0
        snapshot_fingerprint: _JournalFingerprint | None = None
        with self._lock:
            # Validate audit metadata and the journal marker before opening the
            # event stream. A legacy inline-event audit has no journal yet and
            # must still use the historical JSON representation.
            self._read_record(audit_id, include_events=False)
            journal = self._event_journal_path(audit_id)
            if not self._event_journal_exists(journal):
                record = self._read_record(audit_id)
                inline_events = [dict(event) for event in record.get("events") or []]
            else:
                try:
                    fd = os.open(journal, _JOURNAL_READ_FLAGS)
                except OSError as exc:
                    raise ValueError("audit event journal cannot be opened safely") from exc
                try:
                    journal_stat = os.fstat(fd)
                    if not stat.S_ISREG(journal_stat.st_mode):
                        raise ValueError("audit event journal must be a regular file")
                    # append_event() holds this same lock until its newline is
                    # flushed and fsynced, so st_size is always a complete event
                    # boundary for store-managed writes.
                    snapshot_size = journal_stat.st_size
                    snapshot_fingerprint = self._fingerprint(journal_stat)
                except Exception:
                    os.close(fd)
                    fd = -1
                    raise

        if inline_events is not None:
            for event in inline_events:
                visitor(event)
            return len(inline_events)

        pending_ranges: dict[str, _RunRange] = {}
        try:
            count = self._scan_snapshot(
                fd,
                snapshot_size,
                visitor,
                audit_id=audit_id,
                pending_ranges=pending_ranges,
            )
        finally:
            if fd >= 0:
                os.close(fd)

        if snapshot_fingerprint is not None:
            with self._lock:
                self._validated_journals[audit_id] = (snapshot_fingerprint, count)
                self._merge_run_ranges_locked(pending_ranges, persist_updates=True)
        return count

    def validate_events(self, audit_id: str) -> int:
        """Validate one journal once per unchanged filesystem fingerprint."""

        with self._lock:
            self._read_record(audit_id, include_events=False)
            journal = self._event_journal_path(audit_id)
            if self._event_journal_exists(journal):
                current = self._path_fingerprint(journal)
                cached = self._validated_journals.get(audit_id)
                if cached is not None and cached[0] == current:
                    return cached[1]
        return self.scan_events(audit_id, lambda _event: None)

    def indexed_run_events(self, run_id: str) -> tuple[str, list[dict[str, Any]]] | None:
        """Read one correlated run through the trusted range cache when possible.

        The sidecar only points at a byte range. Before seeking into that range,
        Veritas validates the complete authoritative journal for the owning audit
        and requires the journal fingerprint to remain unchanged. A forged or
        stale sidecar therefore cannot bypass journal integrity checks.
        """

        clean_run_id = str(run_id or "").strip()
        if not clean_run_id:
            return None
        with self._lock:
            self._refresh_run_index_locked()
            item = self._run_ranges.get(clean_run_id)
        if item is None:
            return None

        self.validate_events(item.audit_id)
        with self._lock:
            # Full validation may have rebuilt a more complete range.
            self._refresh_run_index_locked()
            item = self._run_ranges.get(clean_run_id)
            if item is None:
                return None
            journal = self._event_journal_path(item.audit_id)
            if not self._event_journal_exists(journal):
                return None
            current = self._path_fingerprint(journal)
            validated = self._validated_journals.get(item.audit_id)
            if validated is None or validated[0] != current:
                return None
            if item.start < 0 or item.end <= item.start or item.end > current.size:
                self._run_ranges.pop(clean_run_id, None)
                return None
            try:
                fd = os.open(journal, _JOURNAL_READ_FLAGS)
            except OSError as exc:
                raise ValueError("audit event journal cannot be opened safely") from exc
            try:
                opened = self._fingerprint(os.fstat(fd))
                if opened != current:
                    return None
                payload = os.pread(fd, item.end - item.start, item.start)
            finally:
                os.close(fd)

        if len(payload) != item.end - item.start:
            return None
        matched: list[dict[str, Any]] = []
        for line_number, raw_line in enumerate(self._iter_range_lines(payload), start=1):
            event = self._decode_event_line(raw_line, line_number)
            if self._event_run_id(event) == clean_run_id:
                matched.append(event)
        if not matched:
            with self._lock:
                self._run_ranges.pop(clean_run_id, None)
            return None
        return item.audit_id, matched

    def append_event(
        self,
        event: HarnessEvent,
        *,
        hydrate_result: bool = False,
    ) -> dict[str, Any]:
        """Append authoritatively, then update only non-authoritative accelerators."""

        audit_id = event.audit_id
        with self._lock:
            journal = self._event_journal_path(audit_id)
            before = (
                self._path_fingerprint(journal)
                if self._event_journal_exists(journal)
                else None
            )
            cached_before = self._validated_journals.get(audit_id)
            result = super().append_event(event, hydrate_result=hydrate_result)
            after = self._path_fingerprint(journal)
            event_dict = event.to_dict()
            rendered_size = len(self._event_line(event_dict).encode("utf-8"))
            pending: dict[str, _RunRange] = {}
            self._merge_pending_run_range(
                pending,
                audit_id,
                event_dict,
                start=max(0, after.size - rendered_size),
                end=after.size,
            )

            # Preserve a warm validation watermark only when the exact journal
            # fingerprint seen before this store-managed append had already been
            # validated. External edits change that fingerprint and force a full
            # scan before any indexed read is trusted again.
            if before is not None and cached_before is not None and cached_before[0] == before:
                self._validated_journals[audit_id] = (after, cached_before[1] + 1)
            else:
                self._validated_journals.pop(audit_id, None)
            self._merge_run_ranges_locked(
                pending,
                persist_updates=self._event_is_terminal_run(event_dict),
            )
            return result

    @staticmethod
    def _scan_snapshot(
        fd: int,
        snapshot_size: int,
        visitor: EventVisitor,
        *,
        audit_id: str | None = None,
        pending_ranges: dict[str, _RunRange] | None = None,
    ) -> int:
        count = 0
        line_number = 0
        remaining = snapshot_size
        buffer = b""
        absolute_offset = 0

        while remaining:
            chunk = os.read(fd, min(_SCAN_CHUNK_BYTES, remaining))
            if not chunk:
                raise ValueError("audit event journal changed during snapshot scan")
            remaining -= len(chunk)
            buffer += chunk

            while True:
                newline = buffer.find(b"\n")
                if newline < 0:
                    break
                raw_line = buffer[:newline]
                line_start = absolute_offset
                line_end = line_start + newline + 1
                buffer = buffer[newline + 1 :]
                absolute_offset = line_end
                line_number += 1
                event = ProductHarnessStore._decode_event_line(raw_line, line_number)
                visitor(event)
                if audit_id is not None and pending_ranges is not None:
                    ProductHarnessStore._merge_pending_run_range(
                        pending_ranges,
                        audit_id,
                        event,
                        start=line_start,
                        end=line_end,
                    )
                count += 1

        # Historical readers accept a valid final JSON record without a trailing
        # newline, even though store-managed appends always write one.
        if buffer:
            line_number += 1
            line_start = absolute_offset
            line_end = line_start + len(buffer)
            event = ProductHarnessStore._decode_event_line(buffer, line_number)
            visitor(event)
            if audit_id is not None and pending_ranges is not None:
                ProductHarnessStore._merge_pending_run_range(
                    pending_ranges,
                    audit_id,
                    event,
                    start=line_start,
                    end=line_end,
                )
            count += 1
        return count

    @staticmethod
    def _decode_event_line(raw_line: bytes, line_number: int) -> dict[str, Any]:
        if not raw_line.strip():
            raise ValueError(f"audit event journal contains a blank line at {line_number}")
        try:
            event = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"audit event journal contains invalid JSON at line {line_number}"
            ) from exc
        if not isinstance(event, dict):
            raise TypeError(
                f"audit event journal entry at line {line_number} must be an object"
            )
        return event

    @staticmethod
    def _event_run_id(event: dict[str, Any]) -> str | None:
        payload = event.get("payload")
        if isinstance(payload, dict):
            value = payload.get("run_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
        if event.get("kind") == "tool":
            value = event.get("event_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _event_is_terminal_run(event: dict[str, Any]) -> bool:
        if event.get("kind") != "tool":
            return False
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return False
        return payload.get("phase") in {"finish", "error", "cancelled"}

    @staticmethod
    def _merge_pending_run_range(
        pending: dict[str, _RunRange],
        audit_id: str,
        event: dict[str, Any],
        *,
        start: int,
        end: int,
    ) -> None:
        run_id = ProductHarnessStore._event_run_id(event)
        if run_id is None:
            return
        current = pending.get(run_id)
        complete = ProductHarnessStore._event_is_terminal_run(event)
        if current is None:
            pending[run_id] = _RunRange(
                audit_id=audit_id,
                start=start,
                end=end,
                complete=complete,
            )
            return
        if current.audit_id != audit_id:
            pending.pop(run_id, None)
            return
        current.start = min(current.start, start)
        current.end = max(current.end, end)
        current.complete = current.complete or complete

    def _merge_run_ranges_locked(
        self,
        pending: dict[str, _RunRange],
        *,
        persist_updates: bool,
    ) -> None:
        if not pending:
            return
        self._refresh_run_index_locked()
        persisted: list[tuple[str, _RunRange]] = []
        for run_id, incoming in pending.items():
            current = self._run_ranges.get(run_id)
            if current is None:
                merged = _RunRange(
                    audit_id=incoming.audit_id,
                    start=incoming.start,
                    end=incoming.end,
                    complete=incoming.complete,
                )
                self._run_ranges[run_id] = merged
                changed = True
                is_new = True
            elif current.audit_id == incoming.audit_id:
                before = (current.start, current.end, current.complete)
                current.start = min(current.start, incoming.start)
                current.end = max(current.end, incoming.end)
                current.complete = current.complete or incoming.complete
                merged = current
                changed = before != (current.start, current.end, current.complete)
                is_new = False
            else:
                # A run id bound to multiple audits is ambiguous. The cache must
                # never choose one; authoritative fallback scanning decides.
                self._run_ranges.pop(run_id, None)
                continue
            if is_new or (persist_updates and changed):
                persisted.append((run_id, merged))
        if persisted:
            self._append_run_index_records_locked(persisted)

    def _refresh_run_index_locked(self) -> None:
        path = self.root / _RUN_INDEX_FILENAME
        try:
            fd = os.open(path, _JOURNAL_READ_FLAGS)
        except FileNotFoundError:
            self._run_index_loaded = True
            self._run_index_fingerprint = None
            return
        except OSError:
            return
        try:
            entry_stat = os.fstat(fd)
            if not stat.S_ISREG(entry_stat.st_mode):
                return
            fingerprint = self._fingerprint(entry_stat)
            if self._run_index_loaded and fingerprint == self._run_index_fingerprint:
                return
            if entry_stat.st_size > _MAX_RUN_INDEX_BYTES:
                self._run_index_loaded = True
                self._run_index_fingerprint = fingerprint
                return
            remaining = entry_stat.st_size
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(fd, min(_SCAN_CHUNK_BYTES, remaining))
                if not chunk:
                    return
                chunks.append(chunk)
                remaining -= len(chunk)
        finally:
            os.close(fd)

        try:
            text = b"".join(chunks).decode("utf-8")
            rebuilt: dict[str, _RunRange] = {}
            for raw_line in text.splitlines():
                if not raw_line.strip():
                    raise ValueError("blank run index line")
                value = json.loads(raw_line)
                if not isinstance(value, dict):
                    raise TypeError("run index entry must be an object")
                if value.get("schema_version") != _RUN_INDEX_SCHEMA_VERSION:
                    raise ValueError("unsupported run index schema")
                run_id = str(value.get("run_id") or "").strip()
                audit_id = str(value.get("audit_id") or "").strip()
                start = value.get("start")
                end = value.get("end")
                if not run_id or not audit_id:
                    raise ValueError("run index entry identity is missing")
                if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
                    raise ValueError("run index byte range is invalid")
                rebuilt[run_id] = _RunRange(
                    audit_id=audit_id,
                    start=start,
                    end=end,
                    complete=bool(value.get("complete")),
                )
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            # Auxiliary index corruption never contaminates authoritative state.
            # Keep current in-memory entries and let journal scans repair them.
            self._run_index_loaded = True
            self._run_index_fingerprint = fingerprint
            return

        for run_id, incoming in rebuilt.items():
            current = self._run_ranges.get(run_id)
            if current is None:
                self._run_ranges[run_id] = incoming
            elif current.audit_id == incoming.audit_id:
                current.start = min(current.start, incoming.start)
                current.end = max(current.end, incoming.end)
                current.complete = current.complete or incoming.complete
            else:
                self._run_ranges.pop(run_id, None)
        self._run_index_loaded = True
        self._run_index_fingerprint = fingerprint

    def _append_run_index_records_locked(
        self,
        values: list[tuple[str, _RunRange]],
    ) -> None:
        path = self.root / _RUN_INDEX_FILENAME
        rendered = "".join(
            json.dumps(
                {
                    "schema_version": _RUN_INDEX_SCHEMA_VERSION,
                    "run_id": run_id,
                    "audit_id": item.audit_id,
                    "start": item.start,
                    "end": item.end,
                    "complete": item.complete,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
            for run_id, item in values
        ).encode("utf-8")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
            try:
                written = 0
                while written < len(rendered):
                    count = os.write(fd, rendered[written:])
                    if count <= 0:
                        raise OSError("run index append made no progress")
                    written += count
                self._run_index_fingerprint = self._fingerprint(os.fstat(fd))
                self._run_index_loaded = True
            finally:
                os.close(fd)
        except OSError:
            # The index is a cache. Authoritative journal writes already
            # succeeded, so cache maintenance must not change product behavior.
            return

    @staticmethod
    def _fingerprint(value: os.stat_result) -> _JournalFingerprint:
        return _JournalFingerprint(
            device=value.st_dev,
            inode=value.st_ino,
            size=value.st_size,
            mtime_ns=value.st_mtime_ns,
            ctime_ns=value.st_ctime_ns,
        )

    def _path_fingerprint(self, path: Path) -> _JournalFingerprint:
        return self._fingerprint(os.stat(path, follow_symlinks=False))

    @staticmethod
    def _iter_range_lines(payload: bytes) -> Iterator[bytes]:
        for raw_line in payload.splitlines(keepends=True):
            yield raw_line[:-1] if raw_line.endswith(b"\n") else raw_line
