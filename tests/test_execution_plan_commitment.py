from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_execution_evidence_json import load_extraction_execution_plan


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_v015_execution_plan_commitment_recomputes_exact_artifact_closure() -> None:
    root = _root()
    capture_path = root / "benchmark/extraction/execution_plan_capture_v0.15.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))

    plan_path = root / capture["execution_plan"]["path"]
    plan = load_extraction_execution_plan(plan_path)

    assert capture["status"] == "pretest_repository_side_execution_plan_archive"
    assert capture["production_authorized"] is False
    assert capture["selected_source_commit_sha"] == (
        "d6ffdf7debd63281e0db5934e3d4b7ebafb98311"
    )
    assert capture["selected_source_commit_ci"] == {
        "workflow": "ci",
        "workflow_run_id": 34097731344,
        "conclusion": "success",
    }

    assert sha256(plan_path.read_bytes()).hexdigest() == capture["execution_plan"][
        "json_file_sha256"
    ]
    assert plan.sha256() == capture["execution_plan"]["canonical_plan_sha256"]
    assert plan.sha256() == "ea34c3840fefd3f3d25c48464f62667ce5525479615b1deea6c019764bdd9a21"

    artifact_fields = {
        "parser_registry": "parser_registry_sha256",
        "numerical_runtime": "numerical_runtime_sha256",
        "execution_command": "execution_command_sha256",
    }
    for artifact_name, plan_field in artifact_fields.items():
        artifact = capture["execution_artifacts"][artifact_name]
        artifact_path = root / artifact["path"]
        actual_sha256 = sha256(artifact_path.read_bytes()).hexdigest()
        assert actual_sha256 == artifact["sha256"]
        assert getattr(plan, plan_field) == actual_sha256

    assert plan.input_artifact_manifest_sha256 == capture["input_artifact_manifest_sha256"]
    manifest_path = root / "benchmark/extraction/extraction_input_artifact_manifest_v0.15.json"
    assert sha256(manifest_path.read_bytes()).hexdigest() == plan.input_artifact_manifest_sha256

    source_tree = capture["execution_artifacts"]["source_tree"]
    assert source_tree["sha256"] == plan.source_tree_sha256
    assert source_tree["builder"] == (
        "git archive --format=tar --prefix=veritas-source/ <selected-source-commit>"
    )

    assert capture["isolation_contract"] == {
        "network_disabled": True,
        "source_mount_read_only": True,
        "credentials_mounted": False,
    }
    assert plan.network_disabled is True
    assert plan.source_mount_read_only is True
    assert plan.credentials_mounted is False
    assert plan.production_authorized is False

    behavior = capture["capture_behavior"]
    assert behavior["reverified_publication_input_manifest_and_files"] is True
    assert behavior["reconstructed_blinded_reviewer_packet"] is True
    assert behavior["rebuilt_source_archive_twice_and_required_byte_equality"] is True
    assert behavior["built_execution_plan_with_repository_builder"] is True
    assert behavior["reverified_execution_plan_against_exact_artifact_bytes"] is True
    assert behavior["executed_v015_development_or_test_predictions"] is False

    assert capture["durable_independent_external_archive"] is False
    assert capture["trusted_commit_to_source_archive_provenance_established"] is False
