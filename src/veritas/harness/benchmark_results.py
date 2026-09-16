from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .benchmark_catalog import benchmark_definition
from .models import utc_now_iso

_RESULT_SCHEMA_VERSION = "1"
_ALLOWED_STATUSES = frozenset({"passed", "failed", "error", "skipped"})
_ALLOWED_SOURCES = frozenset({"ci", "operator"})
_MAX_SOURCE_BYTES = 1024 * 1024
_MAX_METRICS = 64


def _canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _normalized_timestamp(value: object, field: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat().replace("+00:00", "Z"), utc


def _normalized_commit_sha(value: object, *, required: bool) -> str | None:
    if value is None or value == "":
        if required:
            raise ValueError("commit_sha is required for ci results")
        return None
    if not isinstance(value, str):
        raise ValueError("commit_sha must be a string")
    normalized = value.strip().lower()
    if len(normalized) != 40 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError("commit_sha must be a full 40-character hexadecimal Git commit")
    return normalized


def _normalized_run_url(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("run_url must be a string")
    normalized = value.strip()
    if len(normalized) > 1000:
        raise ValueError("run_url is too long")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("run_url must be an absolute http(s) URL")
    return normalized


def _normalized_metrics(value: object) -> dict[str, bool | int | float | str | None]:
    if value is None or value == "":
        return {}
    if not isinstance(value, dict):
        raise ValueError("metrics must be an object")
    if len(value) > _MAX_METRICS:
        raise ValueError(f"metrics must contain at most {_MAX_METRICS} entries")

    normalized: dict[str, bool | int | float | str | None] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip() or len(key.strip()) > 128:
            raise ValueError("metric keys must be non-empty strings up to 128 characters")
        metric_key = key.strip()
        if isinstance(item, bool) or item is None:
            normalized[metric_key] = item
        elif isinstance(item, int):
            normalized[metric_key] = item
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError(f"metric {metric_key} must be finite")
            normalized[metric_key] = item
        elif isinstance(item, str):
            if len(item) > 1000:
                raise ValueError(f"metric {metric_key} string value is too long")
            normalized[metric_key] = item
        else:
            raise ValueError(f"metric {metric_key} must be a JSON scalar")
    return normalized


def validate_benchmark_result_payload(payload: object) -> dict[str, Any]:
    """Validate and canonicalize one Benchmark Result Envelope v1 payload."""

    if not isinstance(payload, dict):
        raise ValueError("benchmark result must be a JSON object")
    if payload.get("schema_version") != _RESULT_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {_RESULT_SCHEMA_VERSION}")

    benchmark_id = payload.get("benchmark_id")
    if not isinstance(benchmark_id, str) or not benchmark_id.strip():
        raise ValueError("benchmark_id is required")
    benchmark_id = benchmark_id.strip()
    definition = benchmark_definition(benchmark_id)

    command = payload.get("command")
    if command != definition["command"]:
        raise ValueError(f"command does not match catalog for {benchmark_id}")

    status = payload.get("status")
    if status not in _ALLOWED_STATUSES:
        raise ValueError("status must be one of passed, failed, error, skipped")

    source = payload.get("source")
    if source not in _ALLOWED_SOURCES:
        raise ValueError("source must be ci or operator")

    started_at, started = _normalized_timestamp(payload.get("started_at"), "started_at")
    finished_at, finished = _normalized_timestamp(payload.get("finished_at"), "finished_at")
    if finished < started:
        raise ValueError("finished_at must not precede started_at")

    commit_sha = _normalized_commit_sha(payload.get("commit_sha"), required=source == "ci")
    run_url = _normalized_run_url(payload.get("run_url"))
    summary = payload.get("summary")
    if summary is None or summary == "":
        summary = None
    elif not isinstance(summary, str):
        raise ValueError("summary must be a string")
    else:
        summary = summary.strip()
        if len(summary) > 4000:
            raise ValueError("summary is too long")

    return {
        "schema_version": _RESULT_SCHEMA_VERSION,
        "benchmark_id": benchmark_id,
        "command": str(definition["command"]),
        "status": status,
        "source": source,
        "started_at": started_at,
        "finished_at": finished_at,
        "commit_sha": commit_sha,
        "run_url": run_url,
        "summary": summary,
        "metrics": _normalized_metrics(payload.get("metrics")),
    }


class BenchmarkResultStore:
    """Append-only local store for validated benchmark execution envelopes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve() / "benchmark-results"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def ingest(self, payload: object, *, source_bytes: bytes | None = None) -> dict[str, Any]:
        if source_bytes is not None and not isinstance(source_bytes, bytes):
            raise TypeError("source_bytes must be bytes")
        if source_bytes is not None and len(source_bytes) > _MAX_SOURCE_BYTES:
            raise ValueError("benchmark result source exceeds 1 MiB")

        validated = validate_benchmark_result_payload(payload)
        payload_bytes = _canonical_json_bytes(validated)
        payload_sha256 = sha256(payload_bytes).hexdigest()
        result_id = f"bmr_{payload_sha256[:16]}"
        definition = benchmark_definition(validated["benchmark_id"])
        started = datetime.fromisoformat(validated["started_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(validated["finished_at"].replace("Z", "+00:00"))
        record = {
            "result_id": result_id,
            "schema_version": _RESULT_SCHEMA_VERSION,
            "payload_sha256": payload_sha256,
            "source_sha256": sha256(source_bytes if source_bytes is not None else payload_bytes).hexdigest(),
            "ingested_at": utc_now_iso(),
            "benchmark_id": validated["benchmark_id"],
            "title": definition["title"],
            "kind": definition["kind"],
            "gating": definition["gating"],
            "command": validated["command"],
            "status": validated["status"],
            "source": validated["source"],
            "started_at": validated["started_at"],
            "finished_at": validated["finished_at"],
            "duration_ms": max(0, round((finished - started).total_seconds() * 1000)),
            "commit_sha": validated["commit_sha"],
            "run_url": validated["run_url"],
            "summary": validated["summary"],
            "metrics": validated["metrics"],
        }

        with self._lock:
            destination = self._result_path(result_id)
            if destination.exists():
                return self._read_result(result_id)
            temporary = destination.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(destination)
            try:
                destination.chmod(0o444)
            except OSError:
                pass
        return dict(record)

    def list_results(
        self,
        *,
        benchmark_id: str | None = None,
        limit: int | None = 100,
    ) -> list[dict[str, Any]]:
        if limit is not None and not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        if benchmark_id is not None:
            benchmark_definition(benchmark_id)

        with self._lock:
            records = [self._read_result(path.stem) for path in self.root.glob("bmr_*.json")]
        if benchmark_id is not None:
            records = [item for item in records if item["benchmark_id"] == benchmark_id]
        records.sort(key=lambda item: str(item["finished_at"]), reverse=True)
        return records if limit is None else records[:limit]

    def get_result(self, result_id: str) -> dict[str, Any]:
        with self._lock:
            return self._read_result(result_id)

    def _result_path(self, result_id: str) -> Path:
        if not result_id.startswith("bmr_") or len(result_id) != 20:
            raise ValueError("invalid benchmark result id")
        suffix = result_id[4:]
        if any(char not in "0123456789abcdef" for char in suffix):
            raise ValueError("invalid benchmark result id")
        return self.root / f"{result_id}.json"

    def _read_result(self, result_id: str) -> dict[str, Any]:
        path = self._result_path(result_id)
        if not path.is_file():
            raise FileNotFoundError(f"benchmark result not found: {result_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("result_id") != result_id:
            raise ValueError("benchmark result metadata is invalid")

        validated = validate_benchmark_result_payload(
            {
                "schema_version": value.get("schema_version"),
                "benchmark_id": value.get("benchmark_id"),
                "command": value.get("command"),
                "status": value.get("status"),
                "source": value.get("source"),
                "started_at": value.get("started_at"),
                "finished_at": value.get("finished_at"),
                "commit_sha": value.get("commit_sha"),
                "run_url": value.get("run_url"),
                "summary": value.get("summary"),
                "metrics": value.get("metrics"),
            }
        )
        payload_sha256 = sha256(_canonical_json_bytes(validated)).hexdigest()
        if payload_sha256 != value.get("payload_sha256"):
            raise ValueError(f"benchmark result hash mismatch: {result_id}")
        if result_id != f"bmr_{payload_sha256[:16]}":
            raise ValueError(f"benchmark result id mismatch: {result_id}")

        definition = benchmark_definition(validated["benchmark_id"])
        if value.get("title") != definition["title"]:
            raise ValueError(f"benchmark result title mismatch: {result_id}")
        if value.get("kind") != definition["kind"] or value.get("gating") != definition["gating"]:
            raise ValueError(f"benchmark result catalog metadata mismatch: {result_id}")

        started = datetime.fromisoformat(validated["started_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(validated["finished_at"].replace("Z", "+00:00"))
        expected_duration = max(0, round((finished - started).total_seconds() * 1000))
        if value.get("duration_ms") != expected_duration:
            raise ValueError(f"benchmark result duration mismatch: {result_id}")
        if not isinstance(value.get("ingested_at"), str):
            raise ValueError(f"benchmark result ingestion metadata invalid: {result_id}")
        _normalized_timestamp(value["ingested_at"], "ingested_at")
        source_sha256 = value.get("source_sha256")
        if not isinstance(source_sha256, str) or len(source_sha256) != 64:
            raise ValueError(f"benchmark result source hash invalid: {result_id}")
        if any(char not in "0123456789abcdef" for char in source_sha256):
            raise ValueError(f"benchmark result source hash invalid: {result_id}")
        return value
