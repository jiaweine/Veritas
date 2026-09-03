from __future__ import annotations

import pytest

from veritas.reproduction_ingest_contract import (
    validate_single_target_ingest_contract,
    validate_target_set_ingest_contract,
)

SOURCE_SHA = "1" * 64
ENV_SHA = "2" * 64
LOCK_SHA = "3" * 64
OUTPUT_SHA = "4" * 64
COMMIT_SHA = "5" * 40
BASE_IMAGE = "python:3.12-slim@sha256:" + "6" * 64


def _packet_base() -> dict:
    return {
        "schema_version": 1,
        "case_id": "case-typed",
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
        "case_id": "case-typed",
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
        "target_id": "beta",
        "claim_id": "claim-main",
        "metric": "coefficient",
        "target_commitment_sha256": "7" * 64,
        "reproduced_value_binding": {
            "format": "csv",
            "row_match": {"currency": "CAD"},
            "value_column": "estimate",
        },
        "reviewer_a_complete": True,
        "reviewer_b_complete": False,
        "adjudication_complete": False,
        "reported_numeric_value_stored_in_repository": False,
    }
    return packet


def _target_set_packet() -> dict:
    packet = _packet_base()
    packet["target_set_contract"] = {
        "target_commitment_sha256": "7" * 64,
        "reproduced_values_format": "strict_target_json_v1",
        "reported_numeric_values_stored_in_repository": False,
        "targets": [
            {
                "target_id": "beta",
                "claim_id": "claim-main",
                "metric": "coefficient",
                "reviewer_a_complete": True,
                "reviewer_b_complete": False,
                "adjudication_complete": False,
            }
        ],
    }
    return packet


def _single_execution() -> dict:
    execution = _execution()
    execution["target_id"] = "beta"
    return execution


def _set_execution() -> dict:
    execution = _execution()
    execution["target_ids"] = ["beta"]
    return execution


def test_packet_schema_version_rejects_boolean_one() -> None:
    packet = _single_packet()
    packet["schema_version"] = True
    with pytest.raises(TypeError, match="schema_version.*integer"):
        validate_single_target_ingest_contract(packet, _single_execution())


def test_execution_exit_code_rejects_boolean_zero() -> None:
    execution = _single_execution()
    execution["exit_code"] = False
    with pytest.raises(TypeError, match="exit_code.*integer"):
        validate_single_target_ingest_contract(_single_packet(), execution)


@pytest.mark.parametrize("field", ["network_disabled", "credentials_mounted"])
def test_execution_security_flags_require_real_booleans(field: str) -> None:
    execution = _single_execution()
    execution[field] = "false"
    with pytest.raises(TypeError, match=f"{field}.*boolean"):
        validate_single_target_ingest_contract(_single_packet(), execution)


def test_packet_hashes_and_git_commit_require_exact_hex() -> None:
    packet = _single_packet()
    packet["replication_package"]["git_commit_sha"] = "G" * 40
    with pytest.raises(ValueError, match="git commit SHA"):
        validate_single_target_ingest_contract(packet, _single_execution())

    packet = _single_packet()
    packet["execution_tracks"]["author_package"]["environment_lock_sha256"] = "x" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        validate_single_target_ingest_contract(packet, _single_execution())


def test_review_flags_require_real_booleans() -> None:
    packet = _single_packet()
    packet["target_contract"]["reviewer_b_complete"] = "false"
    with pytest.raises(TypeError, match="reviewer_b_complete.*boolean"):
        validate_single_target_ingest_contract(packet, _single_execution())


def test_single_execution_optional_value_requires_finite_json_number() -> None:
    execution = _single_execution()
    execution["reproduced_value"] = True
    with pytest.raises(TypeError, match="finite JSON number"):
        validate_single_target_ingest_contract(_single_packet(), execution)

    execution["reproduced_value"] = float("inf")
    with pytest.raises(ValueError, match="must be finite"):
        validate_single_target_ingest_contract(_single_packet(), execution)


def test_csv_binding_rejects_ambiguous_row_match_values() -> None:
    packet = _single_packet()
    packet["target_contract"]["reproduced_value_binding"]["row_match"] = {"currency": True}
    with pytest.raises(TypeError, match="row_match values"):
        validate_single_target_ingest_contract(packet, _single_execution())


def test_json_path_binding_rejects_boolean_index() -> None:
    packet = _single_packet()
    packet["target_contract"]["reproduced_value_binding"] = {
        "format": "json_path",
        "path": ["targets", True, "value"],
    }
    with pytest.raises(TypeError, match="json_path components"):
        validate_single_target_ingest_contract(packet, _single_execution())


def test_target_set_rejects_duplicate_contract_ids() -> None:
    packet = _target_set_packet()
    duplicate = dict(packet["target_set_contract"]["targets"][0])
    packet["target_set_contract"]["targets"].append(duplicate)
    execution = _set_execution()
    execution["target_ids"] = ["beta", "beta"]
    with pytest.raises(ValueError, match="duplicate target_set_contract"):
        validate_target_set_ingest_contract(packet, execution)


def test_target_set_execution_rejects_duplicate_target_ids() -> None:
    packet = _target_set_packet()
    second = dict(packet["target_set_contract"]["targets"][0])
    second["target_id"] = "se"
    second["metric"] = "standard_error"
    packet["target_set_contract"]["targets"].append(second)
    execution = _set_execution()
    execution["target_ids"] = ["beta", "beta"]
    with pytest.raises(ValueError, match="target_ids must be unique"):
        validate_target_set_ingest_contract(packet, execution)


def test_target_set_contract_metadata_boolean_is_typed() -> None:
    packet = _target_set_packet()
    packet["target_set_contract"]["reported_numeric_values_stored_in_repository"] = "false"
    with pytest.raises(TypeError, match="reported_numeric_values.*boolean"):
        validate_target_set_ingest_contract(packet, _set_execution())
