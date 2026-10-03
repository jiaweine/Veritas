from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query

from .benchmark_catalog import benchmark_catalog, benchmark_definition
from .benchmark_results import BenchmarkResultStore

_INDEX_SCHEMA_VERSION = 1
_INDEX_FILENAME = ".benchmark-history-index-v1.json"
_INDEX_MARKER_FILENAME = ".benchmark-history-index-current"
_DEFAULT_PAGE_LIMIT = 50
_MAX_PAGE_LIMIT = 200
_LEGACY_RESULT_LIMIT = 100
_REPLACED_PATHS = frozenset(
    {
        "/api/v1/benchmarks",
        "/api/v1/benchmark-results",
        "/api/v1/benchmark-results/{result_id}",
    }
)


def _canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _index_sha256(payload: dict[str, Any]) -> str:
    value = dict(payload)
    value.pop("index_sha256", None)
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _finished_at_key(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("benchmark history finished_at is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("benchmark history finished_at is invalid")
    return parsed.astimezone(UTC)


def _entry_key(entry: dict[str, str]) -> tuple[datetime, str]:
    return _finished_at_key(entry["finished_at"]), entry["result_id"]


def _cursor_for(entry: dict[str, str]) -> str:
    payload = {
        "v": 1,
        "finished_at": entry["finished_at"],
        "result_id": entry["result_id"],
    }
    rendered = _canonical_json_bytes(payload)
    return base64.urlsafe_b64encode(rendered).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    if not cursor or len(cursor) > 1024:
        raise ValueError("invalid benchmark result cursor")
    padding = "=" * (-len(cursor) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid benchmark result cursor") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise ValueError("invalid benchmark result cursor")
    finished_at = payload.get("finished_at")
    result_id = payload.get("result_id")
    if not isinstance(finished_at, str) or not isinstance(result_id, str):
        raise TypeError("invalid benchmark result cursor")
    if (
        not result_id.startswith("bmr_")
        or len(result_id) != 20
        or any(char not in "0123456789abcdef" for char in result_id[4:])
    ):
        raise ValueError("invalid benchmark result cursor")
    try:
        finished_key = _finished_at_key(finished_at)
    except ValueError as exc:
        raise ValueError("invalid benchmark result cursor") from exc
    return finished_key, result_id


class BenchmarkHistoryIndex:
    """Bounded read model over validated Benchmark Result Envelope files.

    The immutable result envelopes remain the source of truth. The sidecar only
    stores ordering metadata. A missing/stale sidecar is rebuilt under the
    store's shared RLock by fully validating the envelopes once; steady-state
    catalog and history reads then validate only the latest-per-suite records
    or the requested page.
    """

    def __init__(self, store: BenchmarkResultStore) -> None:
        self.store = store
        self.root = store.root
        self.index_path = self.root / _INDEX_FILENAME
        self.marker_path = self.root / _INDEX_MARKER_FILENAME

    def catalog_snapshot(self) -> tuple[int, list[dict[str, Any]]]:
        entries = self._entries()
        latest_entries: list[dict[str, str]] = []
        seen: set[str] = set()
        for entry in entries:
            benchmark_id = entry["benchmark_id"]
            if benchmark_id in seen:
                continue
            seen.add(benchmark_id)
            latest_entries.append(entry)
        latest = [self._verified_entry_result(entry) for entry in latest_entries]
        return len(entries), latest

    def list_results(
        self,
        *,
        benchmark_id: str | None = None,
        limit: int = _LEGACY_RESULT_LIMIT,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= _MAX_PAGE_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_PAGE_LIMIT}")
        entries = self._filtered_entries(benchmark_id)
        return [self._verified_entry_result(entry) for entry in entries[:limit]]

    def page(
        self,
        *,
        benchmark_id: str | None = None,
        limit: int = _DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= _MAX_PAGE_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_PAGE_LIMIT}")
        entries = self._filtered_entries(benchmark_id)
        total = len(entries)
        if cursor:
            key = _decode_cursor(cursor)
            entries = [entry for entry in entries if _entry_key(entry) < key]
        selected = entries[:limit]
        has_more = len(entries) > limit
        items = [self._verified_entry_result(entry) for entry in selected]
        next_cursor = _cursor_for(selected[-1]) if has_more and selected else None
        return {
            "items": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total": total,
        }

    def _verified_entry_result(self, entry: dict[str, str]) -> dict[str, Any]:
        record = self.store.get_result(entry["result_id"])
        for field in ("benchmark_id", "finished_at"):
            if record.get(field) != entry[field]:
                raise ValueError(
                    f"benchmark history index {field} mismatch: {entry['result_id']}"
                )
        return record

    def _filtered_entries(self, benchmark_id: str | None) -> list[dict[str, str]]:
        if benchmark_id is not None:
            benchmark_definition(benchmark_id)
        entries = self._entries()
        if benchmark_id is None:
            return entries
        return [entry for entry in entries if entry["benchmark_id"] == benchmark_id]

    def _entries(self) -> list[dict[str, str]]:
        with self.store._lock:
            if self._needs_rebuild():
                return self._rebuild_locked()
            return self._read_index_locked()

    def _needs_rebuild(self) -> bool:
        if not self.index_path.is_file() or not self.marker_path.is_file():
            return True
        marker_mtime = self.marker_path.stat().st_mtime_ns
        if self.index_path.stat().st_mtime_ns > marker_mtime:
            raise ValueError("benchmark history index changed outside the store")
        return self.root.stat().st_mtime_ns > marker_mtime

    def _rebuild_locked(self) -> list[dict[str, str]]:
        records = self.store.list_results(limit=None)
        entries = [
            {
                "result_id": str(record["result_id"]),
                "benchmark_id": str(record["benchmark_id"]),
                "finished_at": str(record["finished_at"]),
            }
            for record in records
        ]
        entries.sort(key=_entry_key, reverse=True)
        payload: dict[str, Any] = {
            "schema_version": _INDEX_SCHEMA_VERSION,
            "entries": entries,
        }
        payload["index_sha256"] = _index_sha256(payload)
        self._write_index_locked(payload)
        return entries

    def _write_index_locked(self, payload: dict[str, Any]) -> None:
        temporary = self.root / f".benchmark-history-index.{uuid4().hex}.tmp"
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.index_path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

        self.marker_path.touch(exist_ok=True)
        root_mtime = self.root.stat().st_mtime_ns
        os.utime(self.marker_path, ns=(root_mtime + 1, root_mtime + 1))

    def _read_index_locked(self) -> list[dict[str, str]]:
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("benchmark history index is unreadable") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != _INDEX_SCHEMA_VERSION:
            raise ValueError("benchmark history index schema is invalid")
        index_hash = payload.get("index_sha256")
        if not isinstance(index_hash, str) or _index_sha256(payload) != index_hash:
            raise ValueError("benchmark history index hash mismatch")
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise TypeError("benchmark history index entries are invalid")

        entries: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw in raw_entries:
            expected_keys = {"result_id", "benchmark_id", "finished_at"}
            if not isinstance(raw, dict) or set(raw) != expected_keys:
                raise ValueError("benchmark history index entry is invalid")
            result_id = raw.get("result_id")
            benchmark_id = raw.get("benchmark_id")
            finished_at = raw.get("finished_at")
            values = (result_id, benchmark_id, finished_at)
            if not all(isinstance(value, str) and value for value in values):
                raise ValueError("benchmark history index entry is invalid")
            if result_id in seen:
                raise ValueError("benchmark history index contains duplicate result ids")
            seen.add(result_id)
            benchmark_definition(benchmark_id)
            # Reuse the store's path validation without reading the envelope.
            self.store._result_path(result_id)
            entry = {
                "result_id": result_id,
                "benchmark_id": benchmark_id,
                "finished_at": finished_at,
            }
            _entry_key(entry)
            entries.append(entry)

        expected = sorted(entries, key=_entry_key, reverse=True)
        if entries != expected:
            raise ValueError("benchmark history index ordering is invalid")
        return entries


def _remove_legacy_routes(app: FastAPI) -> None:
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) not in _REPLACED_PATHS
    ]


def _integrity_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"benchmark result integrity error: {exc}")


def register_benchmark_pagination_routes(app: FastAPI) -> None:
    """Replace legacy benchmark GET routes with indexed bounded equivalents."""

    store: BenchmarkResultStore = app.state.benchmark_results
    history = BenchmarkHistoryIndex(store)
    app.state.benchmark_history = history
    _remove_legacy_routes(app)

    @app.get("/api/v1/benchmarks")
    def benchmark_inventory() -> dict[str, Any]:
        try:
            result_count, latest = history.catalog_snapshot()
            catalog = benchmark_catalog(latest)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise _integrity_error(exc) from exc
        catalog["result_count"] = result_count
        catalog["results_available"] = result_count > 0
        return catalog

    @app.get("/api/v1/benchmark-results")
    def list_benchmark_results(
        benchmark_id: str | None = None,
        limit: int = Query(default=_LEGACY_RESULT_LIMIT, ge=1, le=_MAX_PAGE_LIMIT),
    ) -> list[dict[str, Any]]:
        if benchmark_id is not None:
            try:
                benchmark_definition(benchmark_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            return history.list_results(benchmark_id=benchmark_id, limit=limit)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise _integrity_error(exc) from exc

    @app.get("/api/v1/benchmark-result-pages")
    def page_benchmark_results(
        benchmark_id: str | None = None,
        limit: int = Query(default=_DEFAULT_PAGE_LIMIT, ge=1, le=_MAX_PAGE_LIMIT),
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if benchmark_id is not None:
            try:
                benchmark_definition(benchmark_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            return history.page(benchmark_id=benchmark_id, limit=limit, cursor=cursor)
        except (TypeError, ValueError) as exc:
            if "cursor" in str(exc):
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            raise _integrity_error(exc) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise _integrity_error(exc) from exc

    @app.get("/api/v1/benchmark-results/{result_id}")
    def benchmark_result_detail(result_id: str) -> dict[str, Any]:
        try:
            return store.get_result(result_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            if "invalid benchmark result id" in str(exc):
                raise HTTPException(status_code=404, detail="benchmark result not found") from exc
            raise _integrity_error(exc) from exc
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            raise _integrity_error(exc) from exc
