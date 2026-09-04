from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path

from .reproduction_runner import ReplicationRuntime


@dataclass(frozen=True)
class DependencyLock:
    kind: str
    sha256: str
    filename: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("dependency lock kind is required")
        if not isinstance(self.filename, str) or not self.filename.strip():
            raise ValueError("dependency lock filename is required")
        if len(self.sha256) != 64 or any(ch not in "0123456789abcdef" for ch in self.sha256):
            raise ValueError("dependency lock sha256 must be lowercase hex")


@dataclass(frozen=True)
class EnvironmentSnapshot:
    runtime: ReplicationRuntime
    runtime_version: str
    platform: str
    image_ref: str
    dependency_lock: DependencyLock
    package_inventory_sha256: str
    package_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, ReplicationRuntime):
            raise TypeError("runtime must be a ReplicationRuntime")
        for label, value in (
            ("runtime_version", self.runtime_version),
            ("platform", self.platform),
            ("image_ref", self.image_ref),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"environment {label} is required")
        if len(self.package_inventory_sha256) != 64:
            raise ValueError("package_inventory_sha256 must be a SHA-256 digest")
        if isinstance(self.package_count, bool) or not isinstance(self.package_count, int):
            raise TypeError("package_count must be an integer")
        if self.package_count < 0:
            raise ValueError("package_count must be non-negative")

    def sha256(self) -> str:
        raw = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            default=lambda value: value.value,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def dependency_lock_from_file(path: str | Path, *, kind: str) -> DependencyLock:
    lock_path = Path(path)
    if not lock_path.is_file():
        raise ValueError("dependency lock path must point to a file")
    return DependencyLock(
        kind=kind,
        sha256=hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        filename=lock_path.name,
    )


def capture_python_environment(
    *,
    lock_path: str | Path,
    image_ref: str,
) -> EnvironmentSnapshot:
    inventory = tuple(sorted(_python_package_inventory()))
    return EnvironmentSnapshot(
        runtime=ReplicationRuntime.PYTHON,
        runtime_version=platform.python_version(),
        platform=platform.platform(),
        image_ref=image_ref,
        dependency_lock=dependency_lock_from_file(lock_path, kind="python"),
        package_inventory_sha256=_inventory_sha256(inventory),
        package_count=len(inventory),
    )


def build_environment_snapshot(
    *,
    runtime: ReplicationRuntime,
    runtime_version: str,
    platform_name: str,
    image_ref: str,
    dependency_lock: DependencyLock,
    package_inventory: tuple[str, ...],
) -> EnvironmentSnapshot:
    normalized = tuple(sorted(_normalize_inventory_line(item) for item in package_inventory))
    return EnvironmentSnapshot(
        runtime=runtime,
        runtime_version=runtime_version,
        platform=platform_name,
        image_ref=image_ref,
        dependency_lock=dependency_lock,
        package_inventory_sha256=_inventory_sha256(normalized),
        package_count=len(normalized),
    )


def _python_package_inventory() -> tuple[str, ...]:
    rows: list[str] = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name") or distribution.metadata.get("Summary")
        if not name:
            continue
        version = distribution.version
        rows.append(f"{name.casefold()}=={version}")
    rows.append(f"python=={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return tuple(rows)


def _normalize_inventory_line(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("package inventory entries must be non-empty strings")
    text = " ".join(value.strip().split())
    if any(ord(char) < 32 for char in text):
        raise ValueError("package inventory entries must not contain control characters")
    return text


def _inventory_sha256(items: tuple[str, ...]) -> str:
    raw = json.dumps(items, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
