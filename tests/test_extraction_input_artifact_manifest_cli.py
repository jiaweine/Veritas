from __future__ import annotations

import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from veritas.extraction_input_artifacts import (
    load_extraction_input_artifact_manifest,
    verify_extraction_input_artifact_manifest,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_build_input_artifact_manifest_cli_hashes_publications(tmp_path: Path) -> None:
    root = tmp_path / "inputs"
    root.mkdir()
    (root / "paper-a.pdf").write_bytes(b"paper-a")
    (root / "paper-b.pdf").write_bytes(b"paper-b")
    output = tmp_path / "input-artifact-manifest.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_input_artifact_manifest.py",
            "--root",
            str(root),
            "--artifact",
            "paper-a=paper-a.pdf",
            "--artifact",
            "paper-b=paper-b.pdf",
            "--output",
            str(output),
        ],
        cwd=_repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    manifest = load_extraction_input_artifact_manifest(output)
    verify_extraction_input_artifact_manifest(manifest, root)
    assert {item.artifact_id for item in manifest.artifacts} == {"paper-a", "paper-b"}
    assert result.stdout.strip() == sha256(output.read_bytes()).hexdigest()


def test_build_input_artifact_manifest_cli_rejects_unsafe_path(tmp_path: Path) -> None:
    root = tmp_path / "inputs"
    root.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_input_artifact_manifest.py",
            "--root",
            str(root),
            "--artifact",
            "escape=../outside.pdf",
            "--output",
            str(tmp_path / "manifest.json"),
        ],
        cwd=_repo_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "safe POSIX relative path" in result.stderr
