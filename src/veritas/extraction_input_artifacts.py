from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = frozenset({"schema_version", "artifacts", "production_authorized"})
_ARTIFACT_KEYS = frozenset({"artifact_id", "relative_path", "sha256", "size_bytes"})


@dataclass(frozen=True)
class ExtractionInputArtifact:
    artifact_id: str
    relative_path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id.strip():
            raise ValueError("input artifact_id must be a non-empty string")
        _require_safe_relative_path(self.relative_path)
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("input artifact sha256 must be a lowercase SHA-256 digest")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise TypeError("input artifact size_bytes must be an integer")
        if self.size_bytes < 0:
            raise ValueError("input artifact size_bytes must be non-negative")


@dataclass(frozen=True)
class ExtractionInputArtifactManifest:
    artifacts: tuple[ExtractionInputArtifact, ...]
    production_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.artifacts, tuple):
            raise TypeError("input artifact manifest artifacts must be a tuple")
        if not self.artifacts:
            raise ValueError("input artifact manifest cannot be empty")
        if any(not isinstance(item, ExtractionInputArtifact) for item in self.artifacts):
            raise TypeError("input artifact manifest contains an unsupported value")
        ids = [item.artifact_id for item in self.artifacts]
        paths = [item.relative_path for item in self.artifacts]
        if len(set(ids)) != len(ids):
            raise ValueError("input artifact manifest artifact_id values must be unique")
        if len(set(paths)) != len(paths):
            raise ValueError("input artifact manifest relative_path values must be unique")
        if type(self.production_authorized) is not bool or self.production_authorized:
            raise ValueError("input artifact manifests are non-production only")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("input artifact manifest schema_version must be an integer")
        if self.schema_version != 1:
            raise ValueError("input artifact manifest schema_version must be 1")


def build_extraction_input_artifact_manifest(
    root: str | Path,
    artifacts: Iterable[tuple[str, str]],
) -> ExtractionInputArtifactManifest:
    root_path = _validated_root(root)
    entries: list[ExtractionInputArtifact] = []
    for artifact_id, relative_path in artifacts:
        _require_safe_relative_path(relative_path)
        path = _resolve_regular_file(root_path, relative_path)
        entries.append(
            ExtractionInputArtifact(
                artifact_id=artifact_id,
                relative_path=relative_path,
                sha256=_file_sha256(path),
                size_bytes=path.stat().st_size,
            )
        )
    return ExtractionInputArtifactManifest(
        artifacts=tuple(sorted(entries, key=lambda item: (item.artifact_id, item.relative_path)))
    )


def verify_extraction_input_artifact_manifest(
    manifest: ExtractionInputArtifactManifest,
    root: str | Path,
) -> None:
    if not isinstance(manifest, ExtractionInputArtifactManifest):
        raise TypeError("manifest must be an ExtractionInputArtifactManifest")
    root_path = _validated_root(root)
    for artifact in manifest.artifacts:
        path = _resolve_regular_file(root_path, artifact.relative_path)
        if path.stat().st_size != artifact.size_bytes:
            raise ValueError(
                f"input artifact size differs from manifest: {artifact.artifact_id!r}"
            )
        if _file_sha256(path) != artifact.sha256:
            raise ValueError(
                f"input artifact bytes differ from manifest: {artifact.artifact_id!r}"
            )


def load_extraction_input_artifact_manifest(
    path: str | Path,
) -> ExtractionInputArtifactManifest:
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("input artifact manifest must be UTF-8 JSON") from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("input artifact manifest must contain valid JSON") from exc
    _require_exact_keys(payload, _MANIFEST_KEYS, label="input artifact manifest")
    artifacts_payload = payload["artifacts"]
    if not isinstance(artifacts_payload, list):
        raise TypeError("input artifact manifest artifacts must be an array")
    artifacts: list[ExtractionInputArtifact] = []
    for index, item in enumerate(artifacts_payload):
        _require_exact_keys(item, _ARTIFACT_KEYS, label=f"input artifact {index}")
        artifacts.append(
            ExtractionInputArtifact(
                artifact_id=item["artifact_id"],
                relative_path=item["relative_path"],
                sha256=item["sha256"],
                size_bytes=item["size_bytes"],
            )
        )
    return ExtractionInputArtifactManifest(
        artifacts=tuple(artifacts),
        production_authorized=payload["production_authorized"],
        schema_version=payload["schema_version"],
    )


def extraction_input_artifact_manifest_payload(
    manifest: ExtractionInputArtifactManifest,
) -> dict[str, object]:
    if not isinstance(manifest, ExtractionInputArtifactManifest):
        raise TypeError("manifest must be an ExtractionInputArtifactManifest")
    return {
        "schema_version": manifest.schema_version,
        "artifacts": [asdict(item) for item in manifest.artifacts],
        "production_authorized": manifest.production_authorized,
    }


def _validated_root(root: str | Path) -> Path:
    root_path = Path(root)
    if root_path.is_symlink():
        raise ValueError("input artifact root must not be a symbolic link")
    resolved = root_path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("input artifact root must be a directory")
    return resolved


def _require_safe_relative_path(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("input artifact relative_path must be a non-empty string")
    if "\\" in value or value.startswith("/"):
        raise ValueError("input artifact relative_path must be a safe POSIX relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("input artifact relative_path must be a safe POSIX relative path")


def _resolve_regular_file(root: Path, relative_path: str) -> Path:
    _require_safe_relative_path(relative_path)
    current = root
    for part in relative_path.split("/"):
        current = current / part
        if current.is_symlink():
            raise ValueError("input artifact paths must not contain symbolic links")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("input artifact path escapes the configured root")
    if not resolved.is_file():
        raise ValueError("input artifact path must reference a regular file")
    return resolved


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key is not allowed: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is not allowed: {value}")


def _require_exact_keys(value: object, expected: frozenset[str], *, label: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        unknown = tuple(sorted(actual - expected))
        raise ValueError(
            f"{label} keys differ from schema; missing={missing!r}, unknown={unknown!r}"
        )
