from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_extraction_evidence_workflow import _workflow_fixture

from veritas.extraction_evidence_plan_json import extraction_evidence_plan_json_payload
from veritas.extraction_execution_artifacts import build_extraction_execution_plan_from_artifacts
from veritas.extraction_execution_evidence_json import extraction_execution_plan_json_payload
from veritas.extraction_external_provenance import ExtractionExternalTrustRoot
from veritas.extraction_external_provenance_json import extraction_external_trust_root_payload
from veritas.extraction_external_trust_policy_json import load_extraction_external_trust_policy
from veritas.extraction_input_artifacts import (
    build_extraction_input_artifact_manifest,
    extraction_input_artifact_manifest_payload,
)

_SOURCE_COMMIT = "a" * 40


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _trust_root_file(tmp_path: Path) -> Path:
    trust_root = ExtractionExternalTrustRoot(
        issuer="institutional-ci",
        runner_identity="trusted-runner-pool",
        repository="jiaweine/Veritas",
        workflow_identity="extraction-evidence-v1",
        public_key_hex="1" * 64,
    )
    path = tmp_path / "trust-root.json"
    path.write_text(
        json.dumps(extraction_external_trust_root_payload(trust_root)),
        encoding="utf-8",
    )
    return path


def _evidence_plan_file(tmp_path: Path) -> tuple[Path, str]:
    fixture = _workflow_fixture()
    plan = fixture["plan"]
    path = tmp_path / "evidence-plan.json"
    path.write_text(
        json.dumps(extraction_evidence_plan_json_payload(plan, fixture["grid"])),
        encoding="utf-8",
    )
    return path, plan.sha256()


def _execution_artifacts(tmp_path: Path) -> dict[str, Path]:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    (input_root / "paper.pdf").write_bytes(b"publication-bytes")
    manifest = build_extraction_input_artifact_manifest(input_root, (("paper", "paper.pdf"),))
    manifest_path = tmp_path / "input-artifact-manifest.json"
    manifest_path.write_text(
        json.dumps(extraction_input_artifact_manifest_payload(manifest)),
        encoding="utf-8",
    )
    payloads = {
        "source_tree": b"source-tree-archive\n",
        "parser_registry": b'{"parser":"table-v1"}\n',
        "numerical_runtime": b'{"python":"3.12"}\n',
        "execution_command": b"python -m veritas.extract --frozen\n",
    }
    result: dict[str, Path] = {
        "input_artifact_manifest": manifest_path,
        "input_artifact_root": input_root,
    }
    for name, payload in payloads.items():
        path = tmp_path / f"{name}.artifact"
        path.write_bytes(payload)
        result[name] = path
    return result


def _execution_plan_file(tmp_path: Path) -> tuple[Path, str, dict[str, Path]]:
    artifacts = _execution_artifacts(tmp_path)
    plan = build_extraction_execution_plan_from_artifacts(**artifacts)
    path = tmp_path / "execution-plan.json"
    path.write_text(
        json.dumps(extraction_execution_plan_json_payload(plan)),
        encoding="utf-8",
    )
    return path, plan.sha256(), artifacts


def _artifact_cli_args(artifacts: dict[str, Path]) -> list[str]:
    return [
        "--input-artifact-manifest",
        str(artifacts["input_artifact_manifest"]),
        "--input-artifact-root",
        str(artifacts["input_artifact_root"]),
        "--source-tree",
        str(artifacts["source_tree"]),
        "--parser-registry",
        str(artifacts["parser_registry"]),
        "--numerical-runtime",
        str(artifacts["numerical_runtime"]),
        "--execution-command",
        str(artifacts["execution_command"]),
    ]


def _policy_command(
    tmp_path: Path,
    *,
    trust_root_path: Path | None = None,
) -> tuple[list[str], str, str, dict[str, Path]]:
    evidence_plan_path, evidence_plan_sha256 = _evidence_plan_file(tmp_path)
    execution_plan_path, execution_plan_sha256, artifacts = _execution_plan_file(tmp_path)
    root_path = trust_root_path or _trust_root_file(tmp_path)
    return (
        [
            sys.executable,
            "scripts/build_extraction_external_trust_policy.py",
            "--policy-id",
            "real-run-v1",
            "--source-commit-sha",
            _SOURCE_COMMIT,
            "--evidence-plan",
            str(evidence_plan_path),
            "--execution-plan",
            str(execution_plan_path),
            *_artifact_cli_args(artifacts),
            "--trust-root",
            str(root_path),
            "--output",
            str(tmp_path / "policy.json"),
        ],
        evidence_plan_sha256,
        execution_plan_sha256,
        artifacts,
    )


def test_build_external_trust_policy_cli_round_trip(tmp_path: Path) -> None:
    args, evidence_plan_sha256, execution_plan_sha256, _ = _policy_command(tmp_path)
    result = subprocess.run(
        args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    policy = load_extraction_external_trust_policy(tmp_path / "policy.json")
    assert policy.policy_id == "real-run-v1"
    assert policy.evidence_plan_sha256 == evidence_plan_sha256
    assert policy.execution_plan_sha256 == execution_plan_sha256
    assert policy.source_commit_sha == _SOURCE_COMMIT
    assert policy.production_authorized is False
    assert result.stdout.strip() == policy.sha256()


def test_build_external_trust_policy_cli_rejects_bad_source_commit(tmp_path: Path) -> None:
    args, _, _, _ = _policy_command(tmp_path)
    args[args.index(_SOURCE_COMMIT)] = "not-a-commit"
    result = subprocess.run(args, cwd=_root(), check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "source commit SHA must be 40 lowercase hexadecimal characters" in result.stderr


def test_build_external_trust_policy_cli_rejects_drifted_plan_archive(tmp_path: Path) -> None:
    args, _, _, _ = _policy_command(tmp_path)
    plan_path = Path(args[args.index("--evidence-plan") + 1])
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["plan"]["split_salt"] = "post-hoc-salt"
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(args, cwd=_root(), check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "does not match archived plan_sha256" in result.stderr


def test_build_external_trust_policy_cli_rejects_artifact_byte_drift(tmp_path: Path) -> None:
    args, _, _, artifacts = _policy_command(tmp_path)
    artifacts["parser_registry"].write_bytes(b'{"parser":"post-hoc-v2"}\n')

    result = subprocess.run(args, cwd=_root(), check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "parser registry differs from archived artifact bytes" in result.stderr


def test_build_external_trust_policy_cli_rejects_publication_byte_drift(
    tmp_path: Path,
) -> None:
    args, _, _, artifacts = _policy_command(tmp_path)
    (artifacts["input_artifact_root"] / "paper.pdf").write_bytes(b"post-hoc-publication")

    result = subprocess.run(args, cwd=_root(), check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "input artifact" in result.stderr


def test_build_external_trust_policy_cli_rejects_unknown_execution_plan_fields(
    tmp_path: Path,
) -> None:
    args, _, _, _ = _policy_command(tmp_path)
    execution_plan_path = Path(args[args.index("--execution-plan") + 1])
    payload = json.loads(execution_plan_path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    execution_plan_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(args, cwd=_root(), check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "keys differ from schema" in result.stderr


def test_build_external_trust_policy_cli_rejects_unknown_root_fields(tmp_path: Path) -> None:
    root_path = _trust_root_file(tmp_path)
    payload = json.loads(root_path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    root_path.write_text(json.dumps(payload), encoding="utf-8")
    args, _, _, _ = _policy_command(tmp_path, trust_root_path=root_path)

    result = subprocess.run(args, cwd=_root(), check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "keys differ from schema" in result.stderr
