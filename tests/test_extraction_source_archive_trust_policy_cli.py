from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from test_extraction_external_trust_policy_cli import (
    _SOURCE_COMMIT,
    _execution_plan_file,
    _root,
    _trust_root_file,
)

from veritas.extraction_source_archive_provenance_json import (
    load_extraction_source_archive_trust_policy,
)


def _policy_command(tmp_path: Path) -> tuple[list[str], str, dict[str, Path]]:
    execution_plan_path, execution_plan_sha256, artifacts = _execution_plan_file(tmp_path)
    return (
        [
            sys.executable,
            "scripts/build_extraction_source_archive_trust_policy.py",
            "--policy-id",
            "source-archive-v1",
            "--source-commit-sha",
            _SOURCE_COMMIT,
            "--execution-plan",
            str(execution_plan_path),
            "--source-tree",
            str(artifacts["source_tree"]),
            "--trust-root",
            str(_trust_root_file(tmp_path)),
            "--output",
            str(tmp_path / "source-archive-policy.json"),
        ],
        execution_plan_sha256,
        artifacts,
    )


def test_build_source_archive_trust_policy_cli_round_trip(tmp_path: Path) -> None:
    args, execution_plan_sha256, _ = _policy_command(tmp_path)
    result = subprocess.run(
        args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    policy = load_extraction_source_archive_trust_policy(
        tmp_path / "source-archive-policy.json"
    )
    assert policy.policy_id == "source-archive-v1"
    assert policy.execution_plan_sha256 == execution_plan_sha256
    assert policy.source_commit_sha == _SOURCE_COMMIT
    assert policy.production_authorized is False
    assert result.stdout.strip() == policy.sha256()


def test_build_source_archive_trust_policy_cli_rejects_source_tree_byte_drift(
    tmp_path: Path,
) -> None:
    args, _, artifacts = _policy_command(tmp_path)
    artifacts["source_tree"].write_bytes(b"post-hoc-source-tree\n")

    result = subprocess.run(args, cwd=_root(), check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "source tree differs from archived artifact bytes" in result.stderr


def test_build_source_archive_trust_policy_cli_rejects_bad_source_commit(
    tmp_path: Path,
) -> None:
    args, _, _ = _policy_command(tmp_path)
    args[args.index(_SOURCE_COMMIT)] = "not-a-commit"

    result = subprocess.run(args, cwd=_root(), check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "source commit SHA must be 40 lowercase hexadecimal characters" in result.stderr
