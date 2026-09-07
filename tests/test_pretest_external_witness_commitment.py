from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_execution_evidence_json import load_extraction_execution_plan


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_v015_pretest_witness_commitment_rehashes_repository_side_pretest_state() -> None:
    root = _root()
    path = root / "benchmark/extraction/pretest_external_witness_commitment_v0.15.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert _sha256(path) == "1f36c2ff4d27ddf82b099ee6ff1a3501a39cd98b554c17f59e7d2b1ebe4fc5d8"
    assert payload["schema_version"] == 1
    assert payload["status"] == (
        "repository_side_pretest_witness_commitment_awaiting_independent_anchor"
    )
    assert payload["production_authorized"] is False
    assert payload["independent_external_anchor_present"] is False
    assert payload["external_trust_root_pinned"] is False
    assert payload["external_trust_policy_built"] is False
    assert payload["trusted_commit_to_source_archive_provenance_established"] is False
    assert payload["executed_v015_development_or_test_predictions"] is False

    sampling = root / "benchmark/corpus/evidence_sampling_frame_v0.15.json"
    seed = root / "benchmark/extraction/evidence_seed_manifest_v0.15.json"
    evidence_plan_path = root / "benchmark/extraction/evidence_plan_v0.15.json"
    pilot_policy = root / "benchmark/extraction/pretest_pilot_threshold_policy_v0.15.json"
    review_commitment = root / "benchmark/extraction/review_packet_commitment_v0.15.json"
    execution_plan_path = root / "benchmark/extraction/extraction_execution_plan_v0.15.json"
    input_manifest = root / "benchmark/extraction/extraction_input_artifact_manifest_v0.15.json"
    parser_registry = root / "benchmark/extraction/execution_artifacts_v0.15/parser_registry.json"
    runtime = root / "benchmark/extraction/execution_artifacts_v0.15/numerical_runtime.json"
    command = root / "benchmark/extraction/execution_artifacts_v0.15/execution_command.json"

    evidence_plan, _ = load_extraction_evidence_plan(evidence_plan_path)
    execution_plan = load_extraction_execution_plan(execution_plan_path)

    assert payload["sampling_frame"]["json_file_sha256"] == _sha256(sampling)
    assert payload["sampling_frame"]["normalized_sha256"] == evidence_plan.sampling_frame_sha256
    assert payload["seed_manifest"]["json_file_sha256"] == _sha256(seed)
    assert payload["seed_manifest"]["target_universe_sha256"] == (
        evidence_plan.seed_target_universe_sha256
    )

    assert payload["evidence_plan"]["canonical_sha256"] == evidence_plan.sha256()
    assert payload["evidence_plan"]["json_file_sha256"] == _sha256(evidence_plan_path)
    assert payload["evidence_plan"]["threshold_grid_sha256"] == (
        evidence_plan.threshold_grid_sha256
    )
    assert payload["pilot_threshold_policy"]["json_file_sha256"] == _sha256(pilot_policy)
    assert payload["review_packets"]["commitment_json_file_sha256"] == _sha256(
        review_commitment
    )

    assert payload["execution_plan"]["canonical_sha256"] == execution_plan.sha256()
    assert payload["execution_plan"]["json_file_sha256"] == _sha256(execution_plan_path)
    assert payload["execution_artifacts"]["input_artifact_manifest_sha256"] == _sha256(
        input_manifest
    )
    assert payload["execution_artifacts"]["parser_registry_sha256"] == _sha256(
        parser_registry
    )
    assert payload["execution_artifacts"]["numerical_runtime_sha256"] == _sha256(runtime)
    assert payload["execution_artifacts"]["execution_command_sha256"] == _sha256(command)
    assert payload["execution_artifacts"]["source_tree_sha256"] == (
        execution_plan.source_tree_sha256
    )
    assert payload["source_commit_sha"] == (
        json.loads(command.read_text(encoding="utf-8"))["source_commit_sha"]
    )

    assert payload["isolation_contract"] == {
        "network_disabled": True,
        "source_mount_read_only": True,
        "credentials_mounted": False,
    }
