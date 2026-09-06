from __future__ import annotations

from pathlib import Path

import pytest

from veritas.extraction_execution_artifacts import (
    build_extraction_execution_plan_from_artifacts,
    extraction_execution_artifact_sha256,
    verify_extraction_execution_plan_artifacts,
)


def _artifact_paths(tmp_path: Path) -> dict[str, Path]:
    payloads = {
        "input_artifact_manifest": b'{"paper.pdf":"abc"}\n',
        "source_tree": b"deterministic-source-tree-archive\n",
        "parser_registry": b'{"parser":"table-v1"}\n',
        "numerical_runtime": b'{"python":"3.12"}\n',
        "execution_command": b"python -m veritas.extract --frozen\n",
    }
    result: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = tmp_path / f"{name}.artifact"
        path.write_bytes(payload)
        result[name] = path
    return result


def test_execution_plan_is_built_from_exact_archived_bytes(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    plan = build_extraction_execution_plan_from_artifacts(**paths)

    assert plan.input_artifact_manifest_sha256 == extraction_execution_artifact_sha256(
        paths["input_artifact_manifest"]
    )
    assert plan.source_tree_sha256 == extraction_execution_artifact_sha256(paths["source_tree"])
    assert plan.network_disabled is True
    assert plan.source_mount_read_only is True
    assert plan.credentials_mounted is False
    verify_extraction_execution_plan_artifacts(plan, **paths)


def test_execution_plan_artifact_verification_rejects_byte_drift(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    plan = build_extraction_execution_plan_from_artifacts(**paths)
    paths["parser_registry"].write_bytes(b'{"parser":"post-hoc-v2"}\n')

    with pytest.raises(ValueError, match="parser registry differs from archived artifact bytes"):
        verify_extraction_execution_plan_artifacts(plan, **paths)


def test_execution_plan_artifact_hash_is_byte_exact(tmp_path: Path) -> None:
    path = tmp_path / "command.txt"
    path.write_bytes(b"run\n")
    first = extraction_execution_artifact_sha256(path)
    path.write_bytes(b"run")
    second = extraction_execution_artifact_sha256(path)
    assert first != second
