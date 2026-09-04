from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from veritas.extraction_external_provenance import ExtractionExternalTrustRoot
from veritas.extraction_external_provenance_json import extraction_external_trust_root_payload
from veritas.extraction_external_trust_policy_json import load_extraction_external_trust_policy


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


def test_build_external_trust_policy_cli_round_trip(tmp_path: Path) -> None:
    output = tmp_path / "policy.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_external_trust_policy.py",
            "--policy-id",
            "real-run-v1",
            "--evidence-plan-sha256",
            "e" * 64,
            "--trust-root",
            str(_trust_root_file(tmp_path)),
            "--output",
            str(output),
        ],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    policy = load_extraction_external_trust_policy(output)
    assert policy.policy_id == "real-run-v1"
    assert policy.evidence_plan_sha256 == "e" * 64
    assert policy.production_authorized is False
    assert result.stdout.strip() == policy.sha256()


def test_build_external_trust_policy_cli_rejects_bad_plan_hash(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_external_trust_policy.py",
            "--policy-id",
            "real-run-v1",
            "--evidence-plan-sha256",
            "not-a-hash",
            "--trust-root",
            str(_trust_root_file(tmp_path)),
            "--output",
            str(tmp_path / "policy.json"),
        ],
        cwd=_root(),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "64 lowercase hex" in result.stderr


def test_build_external_trust_policy_cli_rejects_unknown_root_fields(tmp_path: Path) -> None:
    root_path = _trust_root_file(tmp_path)
    payload = json.loads(root_path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    root_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_external_trust_policy.py",
            "--policy-id",
            "real-run-v1",
            "--evidence-plan-sha256",
            "e" * 64,
            "--trust-root",
            str(root_path),
            "--output",
            str(tmp_path / "policy.json"),
        ],
        cwd=_root(),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "keys differ from schema" in result.stderr
