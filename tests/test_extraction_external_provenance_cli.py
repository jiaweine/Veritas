from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_extraction_evidence_workflow import _workflow_fixture
from test_extraction_external_trust_policy import _policy_fixture

from veritas.extraction_evidence_plan_json import extraction_evidence_plan_json_payload
from veritas.extraction_execution_evidence_json import (
    attested_extraction_evidence_release_receipt_json_payload,
    extraction_execution_plan_json_payload,
)
from veritas.extraction_external_provenance_json import (
    extraction_external_trust_root_payload,
    extraction_signed_external_provenance_payload,
)
from veritas.extraction_external_trust_policy_json import (
    extraction_external_trust_policy_json_payload,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _archived_fixture(tmp_path: Path) -> tuple[list[str], Path, str, str]:
    policy, evidence_plan_sha256, trust_root, execution_plan, attested_release, signed = (
        _policy_fixture()
    )
    workflow = _workflow_fixture()
    assert workflow["plan"].sha256() == evidence_plan_sha256

    evidence_plan_path = tmp_path / "evidence-plan.json"
    trust_root_path = tmp_path / "trust-root.json"
    trust_policy_path = tmp_path / "trust-policy.json"
    signed_path = tmp_path / "signed-provenance.json"
    execution_plan_path = tmp_path / "execution-plan.json"
    attested_release_path = tmp_path / "attested-release.json"
    output_path = tmp_path / "verified-receipt.json"

    _write_json(
        evidence_plan_path,
        extraction_evidence_plan_json_payload(workflow["plan"], workflow["grid"]),
    )
    _write_json(trust_root_path, extraction_external_trust_root_payload(trust_root))
    _write_json(trust_policy_path, extraction_external_trust_policy_json_payload(policy))
    _write_json(signed_path, extraction_signed_external_provenance_payload(signed))
    _write_json(execution_plan_path, extraction_execution_plan_json_payload(execution_plan))
    _write_json(
        attested_release_path,
        attested_extraction_evidence_release_receipt_json_payload(attested_release),
    )

    args = [
        sys.executable,
        "scripts/verify_extraction_external_provenance.py",
        "--evidence-plan",
        str(evidence_plan_path),
        "--trust-root",
        str(trust_root_path),
        "--trust-policy",
        str(trust_policy_path),
        "--signed-provenance",
        str(signed_path),
        "--execution-plan",
        str(execution_plan_path),
        "--attested-release",
        str(attested_release_path),
        "--expected-run-id",
        signed.statement.run_id,
        "--expected-run-attempt",
        str(signed.statement.run_attempt),
        "--expected-commit-sha",
        signed.statement.commit_sha,
        "--output",
        str(output_path),
    ]
    return args, output_path, evidence_plan_sha256, signed.statement.commit_sha


def test_archived_provenance_cli_verifies_exact_precommitted_run(tmp_path: Path) -> None:
    args, output_path, evidence_plan_sha256, _ = _archived_fixture(tmp_path)

    result = subprocess.run(
        args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["receipt"]["evidence_plan_sha256"] == evidence_plan_sha256
    assert payload["receipt"]["production_authorized"] is False
    assert result.stdout.strip() == payload["receipt_sha256"]


def test_archived_provenance_cli_rejects_wrong_expected_commit(tmp_path: Path) -> None:
    args, _, _, commit_sha = _archived_fixture(tmp_path)
    commit_index = args.index(commit_sha)
    args[commit_index] = "f" * 40

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "commit_sha differs from expected commit" in result.stderr
