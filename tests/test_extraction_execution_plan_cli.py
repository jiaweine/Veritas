from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from veritas.extraction_execution_artifacts import extraction_execution_artifact_sha256
from veritas.extraction_execution_evidence_json import load_extraction_execution_plan


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_artifacts(tmp_path: Path) -> dict[str, Path]:
    values = {
        "input-artifact-manifest": b'{"paper.pdf":"abc"}\n',
        "source-tree": b"source-tree-archive\n",
        "parser-registry": b'{"parser":"table-v1"}\n',
        "numerical-runtime": b'{"python":"3.12"}\n',
        "execution-command": b"python -m veritas.extract --frozen\n",
    }
    result: dict[str, Path] = {}
    for name, payload in values.items():
        path = tmp_path / f"{name}.artifact"
        path.write_bytes(payload)
        result[name] = path
    return result


def test_build_execution_plan_cli_hashes_exact_archived_bytes(tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path)
    output = tmp_path / "execution-plan.json"
    args = [
        sys.executable,
        "scripts/build_extraction_execution_plan.py",
        "--input-artifact-manifest",
        str(artifacts["input-artifact-manifest"]),
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
    result = subprocess.run(
        args,
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
