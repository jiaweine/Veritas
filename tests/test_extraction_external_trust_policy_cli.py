from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_extraction_evidence_workflow import _workflow_fixture

from veritas.extraction_evidence_plan_json import extraction_evidence_plan_json_payload
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


def _evidence_plan_file(tmp_path: Path) -> tuple[Path, str]:
    fixture = _workflow_fixture()
    plan = fixture["plan"]
    path = tmp_path / "evidence-plan.json"
    path.write_text(
        json.dumps(extraction_evidence_plan_json_payload(plan, fixture["grid"])),
        encoding="utf-8",
    )
    return path, plan.sha256()


def test_build_external_trust_policy_cli_round_trip(tmp_path: Path) -> None:
    output = tmp_path / "policy.json"
    plan_path, plan_sha256 = _evidence_plan_file(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_external_trust_policy.py",
            "--policy-id",
            "real-run-v1",
            "--evidence-plan",
            str(plan_path),
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
    assert policy.evidence_plan_sha256 == plan_sha256
    assert policy.production_authorized is False
    assert result.stdout.strip() == policy.sha256()


def test_build_external_trust_policy_cli_rejects_drifted_plan_archive(tmp_path: Path) -> None:
    plan_path, _ = _evidence_plan_file(tmp_path)
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["plan"]["split_salt"] = "post-hoc-salt"
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_external_trust_policy.py",
            "--policy-id",
            "real-run-v1",
            "--evidence-plan",
            str(plan_path),
            "--trust-root",
            str(_trust_root_file(tmp_path)),
            "--output",
            str(tmp_path / "policy.json"),
        ],
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "does not match archived plan_sha256" in result.stderr


def test_build_external_trust_policy_cli_rejects_unknown_root_fields(tmp_path: Path) -> None:
    root_path = _trust_root_file(tmp_path)
    payload = json.loads(root_path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    root_path.write_text(json.dumps(payload), encoding="utf-8")
    plan_path, _ = _evidence_plan_file(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_external_trust_policy.py",
            "--policy-id",
            "real-run-v1",
            "--evidence-plan",
            str(plan_path),
            "--trust-root",
            str(root_path),
            "--output",
            str(tmp_path / "policy.json"),
        ],
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "keys differ from schema" in result.stderr
