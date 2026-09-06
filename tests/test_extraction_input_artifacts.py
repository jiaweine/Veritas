from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas.extraction_input_artifacts import (
    build_extraction_input_artifact_manifest,
    extraction_input_artifact_manifest_payload,
    load_extraction_input_artifact_manifest,
    verify_extraction_input_artifact_manifest,
)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "inputs"
    root.mkdir()
    (root / "paper-a.pdf").write_bytes(b"paper-a-bytes")
    nested = root / "supplement"
    nested.mkdir()
    (nested / "paper-b.pdf").write_bytes(b"paper-b-bytes")
    return root


def test_input_artifact_manifest_round_trip_and_verification(tmp_path: Path) -> None:
    root = _root(tmp_path)
    manifest = build_extraction_input_artifact_manifest(
        root,
        (("paper-a", "paper-a.pdf"), ("paper-b", "supplement/paper-b.pdf")),
    )
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(extraction_input_artifact_manifest_payload(manifest)),
        encoding="utf-8",
    )

    loaded = load_extraction_input_artifact_manifest(path)
    assert loaded == manifest
    verify_extraction_input_artifact_manifest(loaded, root)


def test_input_artifact_manifest_rejects_changed_publication_bytes(tmp_path: Path) -> None:
    root = _root(tmp_path)
    manifest = build_extraction_input_artifact_manifest(root, (("paper-a", "paper-a.pdf"),))
    (root / "paper-a.pdf").write_bytes(b"post-hoc-bytes")

    with pytest.raises(ValueError, match="input artifact (size|bytes) differs from manifest"):
        verify_extraction_input_artifact_manifest(manifest, root)


def test_input_artifact_manifest_rejects_path_traversal(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with pytest.raises(ValueError, match="safe POSIX relative path"):
        build_extraction_input_artifact_manifest(root, (("escape", "../outside.pdf"),))


def test_input_artifact_manifest_rejects_symlinked_artifact(tmp_path: Path) -> None:
    root = _root(tmp_path)
    target = root / "paper-a.pdf"
    link = root / "link.pdf"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable on this platform")

    with pytest.raises(ValueError, match="symbolic links"):
        build_extraction_input_artifact_manifest(root, (("link", "link.pdf"),))


def test_input_artifact_manifest_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,"artifacts":[],"production_authorized":false}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate object key"):
        load_extraction_input_artifact_manifest(path)


def test_input_artifact_manifest_rejects_unknown_fields(tmp_path: Path) -> None:
    root = _root(tmp_path)
    manifest = build_extraction_input_artifact_manifest(root, (("paper-a", "paper-a.pdf"),))
    payload = extraction_input_artifact_manifest_payload(manifest)
    payload["unexpected"] = True
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown=.*unexpected"):
        load_extraction_input_artifact_manifest(path)
