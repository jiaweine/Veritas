from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import ReproductionTarget, target_commitment_sha256
from veritas.types import Materiality

SOURCE_SHA = "1" * 64
ENV_SHA = "2" * 64
LOCK_SHA = "3" * 64
COMMIT_SHA = "4" * 40
BASE_IMAGE = "python:3.12-slim@sha256:" + "5" * 64
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_reproduction_certificate.py"


def _target(target_id: str, claim_id: str, value: float) -> ReproductionTarget:
    return ReproductionTarget(
        target_id=target_id,
        claim_id=claim_id,
        metric="p_value",
        reported=ReportedNumber(value, decimals=3),
        source=SourceLocation(artifact_id="paper", section="Results"),
        materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
    )


def _execution(output_sha256: str) -> dict:
    return {
        "case_id": "case-cli",
        "track": "author_package_frozen_environment_rerun",
        "external_git_commit_sha": COMMIT_SHA,
        "source_manifest_sha256": SOURCE_SHA,
        "environment_freeze_sha256": ENV_SHA,
        "environment_lock_sha256": LOCK_SHA,
        "base_image": BASE_IMAGE,
        "output_artifact_sha256": output_sha256,
        "exit_code": 0,
        "network_disabled": True,
        "source_mount_read_only": True,
        "runtime_precommitted": True,
        "credentials_mounted": False,
        "veritas_repository_mounted": False,
    }


def _packet_base(output_sha256: str) -> dict:
    return {
        "case_id": "case-cli",
        "replication_package": {"git_commit_sha": COMMIT_SHA},
        "execution_tracks": {
            "author_package": {
                "base_image": BASE_IMAGE,
                "environment_lock_sha256": LOCK_SHA,
                "frozen_rerun": {
                    "source_manifest_sha256": SOURCE_SHA,
                    "environment_freeze_sha256": ENV_SHA,
                    "output_artifact_sha256": output_sha256,
                },
            }
        },
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_builds_multi_target_answer_free_certificate(tmp_path: Path) -> None:
    targets = (
        _target("cad-p", "claim-fx", 731.245),
        _target("usd-p", "claim-fx", 982.315),
    )
    output = tmp_path / "results.json"
    _write_json(
        output,
        {
            "schema_version": 1,
            "targets": [
                {"target_id": "cad-p", "value": 731.2454},
                {"target_id": "usd-p", "value": 982.3152},
            ],
        },
    )
    output_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()

    packet = _packet_base(output_sha256)
    packet["target_set_contract"] = {
        "target_commitment_sha256": target_commitment_sha256(targets),
        "reproduced_values_format": "strict_target_json_v1",
        "targets": [
            {
                "target_id": target.target_id,
                "claim_id": target.claim_id,
                "metric": target.metric,
                "reviewer_a_complete": True,
                "reviewer_b_complete": False,
                "adjudication_complete": False,
            }
            for target in targets
        ],
    }
    execution = _execution(output_sha256)
    execution["target_ids"] = [target.target_id for target in targets]

    private_targets = tmp_path / "private-targets.json"
    _write_json(
        private_targets,
        {
            "schema_version": 1,
            "targets": [
                {
                    "target_id": target.target_id,
                    "claim_id": target.claim_id,
                    "metric": target.metric,
                    "reported": {
                        "value": target.reported.value,
                        "decimals": target.reported.decimals,
                        "operator": "=",
                    },
                    "source": {"artifact_id": "paper", "section": "Results"},
                    "materiality": int(target.materiality),
                }
                for target in targets
            ],
        },
    )
    packet_path = tmp_path / "packet.json"
    execution_path = tmp_path / "execution.json"
    certificate_path = tmp_path / "certificate.json"
    _write_json(packet_path, packet)
    _write_json(execution_path, execution)

    result = _run_cli(
        "--packet",
        str(packet_path),
        "--execution",
        str(execution_path),
        "--private-target-set",
        str(private_targets),
        "--output-artifact",
        str(output),
        "--certificate-out",
        str(certificate_path),
    )

    assert result.returncode == 0, result.stderr
    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    assert certificate["schema_version"] == 2
    assert certificate["comparison"]["decision"] == "MATCH"
    assert certificate["comparison"]["matched_targets"] == 2
    rendered = certificate_path.read_text(encoding="utf-8") + result.stdout
    for secret in ("731.245", "731.2454", "982.315", "982.3152"):
        assert secret not in rendered


def test_cli_preserves_single_target_mode(tmp_path: Path) -> None:
    target = _target("cad-p", "claim-cad", 731.245)
    output = tmp_path / "results.csv"
    output.write_text("currency,pvalue_cf\nCAD,731.2454\n", encoding="utf-8")
    output_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()

    packet = _packet_base(output_sha256)
    packet["target_contract"] = {
        "target_id": target.target_id,
        "claim_id": target.claim_id,
        "metric": target.metric,
        "target_commitment_sha256": target_commitment_sha256((target,)),
        "reproduced_value_binding": {
            "format": "csv",
            "row_match": {"currency": "CAD"},
            "value_column": "pvalue_cf",
        },
        "reviewer_a_complete": True,
        "reviewer_b_complete": False,
        "adjudication_complete": False,
    }
    execution = _execution(output_sha256)
    execution["target_id"] = target.target_id
    execution["reproduced_value"] = 731.2454

    private_target = tmp_path / "private-target.json"
    _write_json(
        private_target,
        {
            "target_id": target.target_id,
            "claim_id": target.claim_id,
            "metric": target.metric,
            "reported": {"value": 731.245, "decimals": 3, "operator": "="},
            "source": {"artifact_id": "paper", "section": "Results"},
            "materiality": int(target.materiality),
        },
    )
    packet_path = tmp_path / "packet.json"
    execution_path = tmp_path / "execution.json"
    certificate_path = tmp_path / "certificate.json"
    _write_json(packet_path, packet)
    _write_json(execution_path, execution)

    result = _run_cli(
        "--packet",
        str(packet_path),
        "--execution",
        str(execution_path),
        "--private-target",
        str(private_target),
        "--output-artifact",
        str(output),
        "--certificate-out",
        str(certificate_path),
    )

    assert result.returncode == 0, result.stderr
    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    assert certificate["schema_version"] == 1
    assert certificate["comparison"]["decision"] == "MATCH"
    assert "731.245" not in certificate_path.read_text(encoding="utf-8")
