from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from veritas.extraction_execution_artifacts import extraction_execution_artifact_sha256
from veritas.extraction_execution_evidence_json import load_extraction_execution_plan
from veritas.extraction_input_artifacts import (
    build_extraction_input_artifact_manifest,
    extraction_input_artifact_manifest_payload,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_artifacts(tmp_path: Path) -> dict[str, Path]:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    (input_root / "paper.pdf").write_bytes(b"publication-bytes")
    manifest = build_extraction_input_artifact_manifest(input_root, (("paper", "paper.pdf"),))
    manifest_path = tmp_path / "input-artifact-manifest.json"
    manifest_path.write_text(
        json.dumps(extraction_input_artifact_manifest_payload(manifest)),
        encoding="utf-8",
    )
    values = {
        "source-tree": b"source-tree-archive\n",
        "parser-registry": b'{"parser":"table-v1"}\n',
        "numerical-runtime": b'{"python":"3.12"}\n',
        "execution-command": b"python -m veritas.extract --frozen\n",
    }
    result: dict[str, Path] = {
        "input-artifact-manifest": manifest_path,
        "input-artifact-root": input_root,
    }
    for name, payload in values.items():
        path = tmp_path / f"{name}.artifact"
        path.write_bytes(payload)
        result[name] = path
    return result


def _command(artifacts: dict[str, Path], output: Path) -> list[str]:
    return [
        sys.executable,
        "scripts/build_extraction_execution_plan.py",
        "--input-artifact-manifest",
        str(artifacts["input-artifact-manifest"]),
        "--input-artifact-root",
        str(artifacts["input-artifact-root"]),
        "--source-tree",
        str(artifacts["source-tree"]),
        "--parser-registry",
        str(artifacts["parser-registry"]),
        "--numerical-runtime",
        str(artifacts["numerical-runtime"]),
        "--execution-command",
        str(artifacts["execution-command"]),
        "--output",
        str(output),
    ]


def test_build_execution_plan_cli_hashes_exact_verified_bytes(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    output = tmp_path / "execution-plan.json"
    result = subprocess.run(
        _command(artifacts, output),
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    plan = load_extraction_execution_plan(output)
    assert plan.input_artifact_manifest_sha256 == extraction_execution_artifact_sha256(
        artifacts["input-artifact-manifest"]
    )
    assert plan.source_tree_sha256 == extraction_execution_artifact_sha256(
        artifacts["source-tree"]
    )
    assert result.stdout.strip() == plan.sha256()


def test_build_execution_plan_cli_rejects_publication_byte_drift(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    (artifacts["input-artifact-root"] / "paper.pdf").write_bytes(b"changed-publication")

    result = subprocess.run(
        _command(artifacts, tmp_path / "execution-plan.json"),
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "input artifact" in result.stderr
