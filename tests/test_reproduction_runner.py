from __future__ import annotations

from pathlib import Path

import pytest

from veritas.reproduction import SandboxPolicy
from veritas.reproduction_runner import (
    ContainerIsolationBackend,
    ReplicationRunnerSpec,
    ReplicationRuntime,
    tree_sha256,
)


def _image(name: str = "python:3.12") -> str:
    return f"{name}@sha256:{'a' * 64}"


def _source(tmp_path: Path, name: str) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / name).write_text("print('ok')\n", encoding="utf-8")
    return source


def test_python_runner_command_enforces_network_and_read_only_source(tmp_path: Path) -> None:
    source = _source(tmp_path, "analysis.py")
    output = tmp_path / "output"
    spec = ReplicationRunnerSpec(
        ReplicationRuntime.PYTHON,
        _image(),
        "analysis.py",
        "b" * 64,
    )

    command = ContainerIsolationBackend(binary="docker").build_command(
        spec,
        source_dir=source,
        output_dir=output,
    )

    rendered = " ".join(command)
    assert "--network none" in rendered
    assert "--read-only" in command
    assert "--cap-drop ALL" in rendered
    assert "no-new-privileges" in rendered
    assert f"src={source.resolve()},dst=/input,readonly" in rendered
    assert f"src={output.resolve()},dst=/output" in rendered
    assert command[-2:] == ("python", "/input/analysis.py")


def test_r_runner_uses_vanilla_rscript(tmp_path: Path) -> None:
    source = _source(tmp_path, "analysis.R")
    spec = ReplicationRunnerSpec(
        ReplicationRuntime.R,
        _image("r-veritas"),
        "analysis.R",
        "c" * 64,
    )

    command = ContainerIsolationBackend().build_command(
        spec,
        source_dir=source,
        output_dir=tmp_path / "out",
    )

    assert command[-3:] == ("Rscript", "--vanilla", "/input/analysis.R")


def test_stata_adapter_requires_explicit_license_authorization(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="licensed-runtime authorization"):
        ReplicationRunnerSpec(
            ReplicationRuntime.STATA,
            _image("stata-runtime"),
            "analysis.do",
            "d" * 64,
        )

    source = _source(tmp_path, "analysis.do")
    spec = ReplicationRunnerSpec(
        ReplicationRuntime.STATA,
        _image("stata-runtime"),
        "analysis.do",
        "d" * 64,
        stata_license_authorized=True,
    )
    command = ContainerIsolationBackend().build_command(
        spec,
        source_dir=source,
        output_dir=tmp_path / "out",
    )
    assert command[-4:] == ("stata-mp", "-b", "do", "/input/analysis.do")


def test_runner_rejects_weakened_sandbox_policy(tmp_path: Path) -> None:
    source = _source(tmp_path, "analysis.py")
    spec = ReplicationRunnerSpec(
        ReplicationRuntime.PYTHON,
        _image(),
        "analysis.py",
        "b" * 64,
    )

    with pytest.raises(ValueError, match="network_disabled=True"):
        ContainerIsolationBackend().build_command(
            spec,
            source_dir=source,
            output_dir=tmp_path / "out",
            policy=SandboxPolicy(network_disabled=False),
        )


def test_runner_rejects_unpinned_image_and_parent_entrypoint() -> None:
    with pytest.raises(ValueError, match="pinned"):
        ReplicationRunnerSpec(
            ReplicationRuntime.PYTHON,
            "python:3.12",
            "analysis.py",
            "b" * 64,
        )
    with pytest.raises(ValueError, match="source mount"):
        ReplicationRunnerSpec(
            ReplicationRuntime.PYTHON,
            _image(),
            "../analysis.py",
            "b" * 64,
        )


def test_tree_sha256_binds_relative_paths_and_bytes(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "a.txt").write_text("one", encoding="utf-8")
    first = tree_sha256(root)
    (root / "a.txt").write_text("two", encoding="utf-8")
    second = tree_sha256(root)

    assert first != second
