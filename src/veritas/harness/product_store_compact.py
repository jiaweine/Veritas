from __future__ import annotations

import json
import os
import stat
from uuid import uuid4

from .product_store import (
    _MAX_RUN_INDEX_BYTES,
    _RUN_INDEX_FILENAME,
    _RUN_INDEX_SCHEMA_VERSION,
    ProductHarnessStore as _BaseProductHarnessStore,
    _RunRange,
)

_RUN_INDEX_COMPACT_BYTES = 8 * 1024 * 1024
_RUN_INDEX_COMPACT_STALE_RATIO = 2


class ProductHarnessStore(_BaseProductHarnessStore):
    """Product store with bounded, atomic maintenance for the auxiliary run index.

    The run index is only an accelerator. Compaction is therefore best-effort:
    authoritative journal appends must remain successful even when sidecar
    maintenance cannot run. A compacted file contains at most one current range
    per in-memory run id and is replaced atomically after fsync.
    """

    def _append_run_index_records_locked(
        self,
        values: list[tuple[str, _RunRange]],
    ) -> None:
        super()._append_run_index_records_locked(values)
        try:
            self._maybe_compact_run_index_locked()
        except (OSError, TypeError, ValueError):
            # Cache maintenance must never change authoritative product behavior.
            return

    def compact_run_index(self) -> bool:
        """Best-effort explicit compaction hook used by maintenance and tests."""

        with self._lock:
            self._refresh_run_index_locked()
            try:
                return self._compact_run_index_locked(force=True)
            except (OSError, TypeError, ValueError):
                return False

    def _maybe_compact_run_index_locked(self) -> bool:
        path = self.root / _RUN_INDEX_FILENAME
        try:
            current = os.lstat(path)
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
            return False
        if current.st_size < _RUN_INDEX_COMPACT_BYTES:
            return False
        return self._compact_run_index_locked(force=False, current_size=current.st_size)

    def _compact_run_index_locked(
        self,
        *,
        force: bool,
        current_size: int | None = None,
    ) -> bool:
        path = self.root / _RUN_INDEX_FILENAME
        if current_size is None:
            try:
                current = os.lstat(path)
            except FileNotFoundError:
                return False
            if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
                return False
            current_size = current.st_size

        rendered = self._render_compacted_index()
        if len(rendered) > _MAX_RUN_INDEX_BYTES:
            return False
        if not force:
            if current_size < _RUN_INDEX_COMPACT_BYTES:
                return False
            if len(rendered) * _RUN_INDEX_COMPACT_STALE_RATIO >= current_size:
                return False

        temporary = self.root / f".{_RUN_INDEX_FILENAME}.{uuid4().hex}.compact.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = -1
        try:
            fd = os.open(temporary, flags, 0o600)
            written = 0
            while written < len(rendered):
                count = os.write(fd, rendered[written:])
                if count <= 0:
                    raise OSError("run index compaction made no progress")
                written += count
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.replace(temporary, path)
            replaced = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(replaced.st_mode):
                return False
            self._run_index_fingerprint = self._fingerprint(replaced)
            self._run_index_loaded = True
            return True
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _render_compacted_index(self) -> bytes:
        lines: list[str] = []
        for run_id, item in sorted(self._run_ranges.items()):
            clean_run_id = str(run_id or "").strip()
            clean_audit_id = str(item.audit_id or "").strip()
            if not clean_run_id or not clean_audit_id:
                continue
            if item.start < 0 or item.end <= item.start:
                continue
            lines.append(
                json.dumps(
                    {
                        "schema_version": _RUN_INDEX_SCHEMA_VERSION,
                        "run_id": clean_run_id,
                        "audit_id": clean_audit_id,
                        "start": item.start,
                        "end": item.end,
                        "complete": bool(item.complete),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
        return "".join(lines).encode("utf-8")
