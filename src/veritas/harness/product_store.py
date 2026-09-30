from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from typing import Any

from .store import HarnessStore, _JOURNAL_READ_FLAGS

EventVisitor = Callable[[dict[str, Any]], None]


class ProductHarnessStore(HarnessStore):
    """HarnessStore variant with integrity-preserving streaming event scans.

    Product projections often need to inspect every persisted event but retain
    only a tiny derived result. ``HarnessStore.get_events()`` intentionally
    returns a list for compatibility; this scanner keeps that contract intact
    while giving the web/mobile runtime a zero-history-retention path.
    """

    def scan_events(self, audit_id: str, visitor: EventVisitor) -> int:
        if not callable(visitor):
            raise TypeError("event visitor must be callable")

        with self._lock:
            # Validate audit metadata and the journal marker before opening the
            # event stream. A legacy inline-event audit has no journal yet and
            # must still use the historical JSON representation.
            self._read_record(audit_id, include_events=False)
            journal = self._event_journal_path(audit_id)
            if not self._event_journal_exists(journal):
                record = self._read_record(audit_id)
                count = 0
                for event in record.get("events") or []:
                    visitor(dict(event))
                    count += 1
                return count

            try:
                fd = os.open(journal, _JOURNAL_READ_FLAGS)
            except OSError as exc:
                raise ValueError("audit event journal cannot be opened safely") from exc

            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ValueError("audit event journal must be a regular file")
                count = 0
                with os.fdopen(fd, "r", encoding="utf-8") as handle:
                    fd = -1
                    for line_number, line in enumerate(handle, start=1):
                        if not line.strip():
                            raise ValueError(
                                f"audit event journal contains a blank line at {line_number}"
                            )
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ValueError(
                                "audit event journal contains invalid JSON "
                                f"at line {line_number}"
                            ) from exc
                        if not isinstance(event, dict):
                            raise TypeError(
                                "audit event journal entry at line "
                                f"{line_number} must be an object"
                            )
                        visitor(event)
                        count += 1
                return count
            finally:
                if fd >= 0:
                    os.close(fd)
