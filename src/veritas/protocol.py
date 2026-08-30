from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ProtocolDriftError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditProtocol:
    protocol_version: int = 2
    detector_versions: dict[str, str] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    assumptions: dict[str, Any] = field(default_factory=dict)
    artifact_sha256: dict[str, str] = field(default_factory=dict)
    methodology_snapshot_sha256: str | None = None


def stable_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_protocol_lock(protocol: AuditProtocol) -> dict[str, Any]:
    payload = asdict(protocol)
    return {
        "lock_version": 2,
        "protocol_sha256": stable_sha256(payload),
        "protocol": payload,
    }


def ensure_protocol_lock(path: str | Path, protocol: AuditProtocol) -> dict[str, Any]:
    """Create an immutable audit lock or verify identity with an existing one."""
    target = Path(path)
    desired = build_protocol_lock(protocol)
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        recorded = existing.get("protocol_sha256")
        actual = stable_sha256(existing.get("protocol"))
        if recorded != actual:
            raise ProtocolDriftError("existing protocol lock failed integrity verification")
        if existing.get("protocol") != desired["protocol"]:
            raise ProtocolDriftError("audit protocol drift detected; start a new audit run")
        return existing

    target.parent.mkdir(parents=True, exist_ok=True)
    desired["locked_at"] = datetime.now(UTC).isoformat()
    desired["rule"] = (
        "Changing a locked detector version, threshold, assumption, artifact identity, or methodology snapshot "
        "requires a new audit run."
    )
    target.write_text(json.dumps(desired, ensure_ascii=False, indent=2), encoding="utf-8")
    return desired
