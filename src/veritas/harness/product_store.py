from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from typing import Any

from .store import _JOURNAL_READ_FLAGS, HarnessStore

EventVisitor = Callable[[dict[str, Any]], None]
_SCAN_CHUNK_BYTES = 64 * 1024


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
    """

    def scan_events(self, audit_id: str, visitor: EventVisitor) -> int:
        if not callable(visitor):
            raise TypeError("event visitor must be callable")

        inline_events: list[dict[str, Any]] | None = None
        fd = -1
        snapshot_size = 0
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
                except Exception:
                    os.close(fd)
                    fd = -1
                    raise

        if inline_events is not None:
            for event in inline_events:
                visitor(event)
            return len(inline_events)

        try:
            return self._scan_snapshot(fd, snapshot_size, visitor)
        finally:
            if fd >= 0:
                os.close(fd)

    @staticmethod
    def _scan_snapshot(fd: int, snapshot_size: int, visitor: EventVisitor) -> int:
        count = 0
        line_number = 0
        remaining = snapshot_size
        buffer = b""

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
                buffer = buffer[newline + 1 :]
                line_number += 1
                event = ProductHarnessStore._decode_event_line(raw_line, line_number)
                visitor(event)
                count += 1

        # Historical readers accept a valid final JSON record without a trailing
        # newline, even though store-managed appends always write one.
        if buffer:
            line_number += 1
            event = ProductHarnessStore._decode_event_line(buffer, line_number)
            visitor(event)
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
