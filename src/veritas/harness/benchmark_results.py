from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from .benchmark_catalog import BENCHMARK_CATALOG_SCHEMA_VERSION, benchmark_suite
from .models import utc_now_iso

BENCHMARK_RESULT_SCHEMA_VERSION = "1"
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")


class BenchmarkResultStore:
    """Append-only local provenance for benchmark executions.

    This store records execution facts for repository-known benchmark suites. It
    deliberately does not execute benchmark commands and does not define or
    synthesize benchmark scores.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def record(
        self,
        *,
        benchmark_id: str,
        exit_code: int,
        commit_sha: str | None = None,
        duration_ms: int | None = None,
        recorded_at: str | None = None,
    ) -> dict[str, Any]:
        suite = benchmark_suite(benchmark_id)
        if suite is None:
            raise ValueError(f"unknown benchmark id: {benchmark_id}")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise TypeError("exit_code must be an integer")
        if duration_ms is not None and (
            isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0
        ):
            raise ValueError("duration_ms must be a non-negative integer")

        normalized_commit = self._normalize_commit(commit_sha)
        timestamp = self._normalize_timestamp(recorded_at or utc_now_iso())
        result_id = f"bresult_{uuid4().hex[:16]}"
        payload: dict[str, Any] = {
            "schema_version": BENCHMARK_RESULT_SCHEMA_VERSION,
            "result_id": result_id,
            "benchmark_catalog_schema_version": BENCHMARK_CATALOG_SCHEMA_VERSION,
            "benchmark_id": benchmark_id,
            "title": suite["title"],
            "kind": suite["kind"],
            "gating": bool(suite["gating"]),
            "command": suite["command"],
            "source": suite["source"],
            "status": "passed" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "commit_sha": normalized_commit,
            "duration_ms": duration_ms,
            "recorded_at": timestamp,
        }
        payload["payload_sha256"] = self._payload_sha256(payload)

        with self._lock:
            suite_dir = self.root / benchmark_id
            suite_dir.mkdir(parents=True, exist_ok=True)
            destination = suite_dir / f"{result_id}.json"
            temporary = suite_dir / f".{result_id}.tmp"
            temporary.write_text(self._canonical_json(payload) + "\n", encoding="utf-8")
            temporary.replace(destination)
            try:
                destination.chmod(0o444)
            except OSError:
                pass
        return dict(payload)

    def list_results(
        self,
        *,
        benchmark_id: str | None = None,
        limit: int | None = 100,
    ) -> list[dict[str, Any]]:
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500
        ):
            raise ValueError("limit must be between 1 and 500")
        if benchmark_id is not None and benchmark_suite(benchmark_id) is None:
            raise ValueError(f"unknown benchmark id: {benchmark_id}")

        with self._lock:
            if benchmark_id is None:
                paths = list(self.root.glob("*/bresult_*.json"))
            else:
                paths = list((self.root / benchmark_id).glob("bresult_*.json"))
            results = [self._read_result(path) for path in paths]

        results.sort(
            key=lambda item: (str(item["recorded_at"]), str(item["result_id"])),
            reverse=True,
        )
        return results if limit is None else results[:limit]

    def _read_result(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid benchmark result file: {path.name}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"invalid benchmark result object: {path.name}")
        if payload.get("schema_version") != BENCHMARK_RESULT_SCHEMA_VERSION:
            raise ValueError(f"unsupported benchmark result schema: {path.name}")
        result_id = payload.get("result_id")
        benchmark_id = payload.get("benchmark_id")
        if not isinstance(result_id, str) or path.name != f"{result_id}.json":
            raise ValueError(f"benchmark result id mismatch: {path.name}")
        if not isinstance(benchmark_id, str) or path.parent.name != benchmark_id:
            raise ValueError(f"benchmark result suite mismatch: {path.name}")
        expected = payload.get("payload_sha256")
        actual = self._payload_sha256(payload)
        if not isinstance(expected, str) or expected != actual:
            raise ValueError(f"benchmark result hash mismatch: {result_id}")
        self._normalize_timestamp(str(payload.get("recorded_at") or ""))
        return dict(payload)

    @staticmethod
    def _normalize_commit(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not _COMMIT_RE.fullmatch(normalized):
            raise ValueError("commit_sha must be a 7-64 character hexadecimal Git commit id")
        return normalized

    @staticmethod
    def _normalize_timestamp(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("recorded_at must not be empty")
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("recorded_at must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            raise ValueError("recorded_at must include a timezone")
        return normalized

    @classmethod
    def _payload_sha256(cls, payload: dict[str, Any]) -> str:
        material = {key: value for key, value in payload.items() if key != "payload_sha256"}
        return sha256(cls._canonical_json(material).encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
