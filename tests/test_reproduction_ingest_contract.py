from __future__ import annotations

from pathlib import Path

import pytest

from veritas.reproduction_ingest_contract import (
    validate_single_target_ingest_contract,
    validate_target_set_ingest_contract,
)
from veritas.reproduction_json import load_strict_reproduction_json

SOURCE_SHA = "1" * 64
ENV_SHA = "2" * 64
LOCK_SHA = "3" * 64
OUTPUT_SHA = "4" * 64
COMMIT_SHA = "5" * 40
BASE_IMAGE = "python:3.12-slim@sha256:" + "6" * 64


def _packet_base() -> dict:
    return {
        "case_id": "case-schema",
        "replication_package": {"git_commit_sha": COMMIT_SHA},
        "execution_tracks": {
            "author_package": {
                "base_image": BASE_IMAGE,
                "environment_lock_sha256": LOCK_SHA,
                "frozen_rerun": {
                    "source_manifest_sha256": SOURCE_SHA,
                    "environment_freeze_sha256": ENV_SHA,
                    "output_artifact_sha256": OUTPUT_SHA,
                },
            }
        },
    }


def _execution() -> dict:
    return {
        "case_id": "case-schema",
        "track": "author_package_frozen_environment_rerun",
        "external_git_commit_sha": COMMIT_SHA,
        "source_manifest_sha256": SOURCE_SHA,
        "environment_freeze_sha256": ENV_SHA,
        "environment_lock_sha256": LOCK_SHA,
        "base_image": BASE_IMAGE,
        "output_artifact_sha256": OUTPUT_SHA,
        "exit_code": 0,
        "network_disabled": True,
        "source_mount_read_only": True,
        "runtime_precommitted": True,
        "credentials_mounted": False,
        "veritas_repository_mounted": False,
    }


def _single_packet() -> dict:
    packet = _packet_base()
    packet["target_contract"] = {
        "target_id": "cad-p",
        "claim_id": "claim-cad",
        "metric": "p_value",
        "target_commitment_sha256": "7" * 64,
        "reproduced_value_binding": {
            "format": "csv",
            "row_match": {"currency": "CAD"},
            "value_column": "pvalue_cf",
        },
        "reviewer_a_complete": True,
        "reviewer_b_complete": False,
        "adjudication_complete": False,
    }
    return packet


def _target_set_packet() -> dict:
    packet = _packet_base()
    packet["target_set_contract"] = {
        "target_commitment_sha256": "7" * 64,
        "reproduced_values_format": "strict_target_json_v1",
        "targets": [
            {
                "target_id": "cad-p",
                "claim_id": "claim-cad",
                "metric": "p_value",
                "reviewer_a_complete": True,
                "reviewer_b_complete": False,
                "adjudication_complete": False,
            }
        ],
    }
    return packet


def test_single_target_contract_rejects_unknown_execution_fields() -> None:
    execution = _execution()
    execution["target_id"] = "cad-p"
    execution["paper_reported_value"] = 0.049

    with pytest.raises(ValueError, match="unexpected fields"):
        validate_single_target_ingest_contract(_single_packet(), execution)


def test_single_target_contract_rejects_unknown_binding_fields() -> None:
    packet = _single_packet()
    packet["target_contract"]["reproduced_value_binding"]["fallback_value"] = 0.049
    execution = _execution()
    execution["target_id"] = "cad-p"

    with pytest.raises(ValueError, match="unexpected fields"):
        validate_single_target_ingest_contract(packet, execution)


def test_single_target_contract_rejects_ambiguous_target_modes() -> None:
    packet = _single_packet()
    packet["target_set_contract"] = _target_set_packet()["target_set_contract"]
    execution = _execution()
    execution["target_id"] = "cad-p"

    with pytest.raises(ValueError, match="must not also contain target_set_contract"):
        validate_single_target_ingest_contract(packet, execution)


def test_target_set_contract_rejects_unknown_row_fields() -> None:
    packet = _target_set_packet()
    packet["target_set_contract"]["targets"][0]["reported_value"] = 0.049
    execution = _execution()
    execution["target_ids"] = ["cad-p"]

    with pytest.raises(ValueError, match="unexpected fields"):
        validate_target_set_ingest_contract(packet, execution)


def test_target_set_contract_preserves_numeric_side_channel_rejection() -> None:
    execution = _execution()
    execution["target_ids"] = ["cad-p"]
    execution["reproduced_values"] = {"cad-p": 0.049}

    with pytest.raises(ValueError, match="must not duplicate"):
        validate_target_set_ingest_contract(_target_set_packet(), execution)


def test_packet_schema_version_fails_closed_when_present() -> None:
    packet = _single_packet()
    packet["schema_version"] = 2
    execution = _execution()
    execution["target_id"] = "cad-p"

    with pytest.raises(ValueError, match="schema_version"):
        validate_single_target_ingest_contract(packet, execution)


def test_real_benchmark_packet_keeps_provenance_extensions() -> None:
    root = Path(__file__).resolve().parents[1]
    packet = load_strict_reproduction_json(
        root / "benchmark/reproduction/cases/ssrn_7138278_model_lb_v1.3.1_v0.11.json"
    )
    author_track = packet["execution_tracks"]["author_package"]
    frozen = author_track["frozen_rerun"]
    execution = {
        "case_id": packet["case_id"],
        "track": "author_package_frozen_environment_rerun",
        "external_git_commit_sha": packet["replication_package"]["git_commit_sha"],
        "source_manifest_sha256": frozen["source_manifest_sha256"],
        "environment_freeze_sha256": frozen["environment_freeze_sha256"],
        "environment_lock_sha256": author_track["environment_lock_sha256"],
        "base_image": author_track["base_image"],
        "output_artifact_sha256": frozen["output_artifact_sha256"],
        "target_id": packet["target_contract"]["target_id"],
        "exit_code": 0,
        "network_disabled": True,
        "source_mount_read_only": True,
        "runtime_precommitted": True,
        "credentials_mounted": False,
        "veritas_repository_mounted": False,
    }

    validate_single_target_ingest_contract(packet, execution)
