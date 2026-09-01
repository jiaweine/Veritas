from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CASES = _REPO_ROOT / "benchmark" / "reproduction" / "cases"
_FORBIDDEN_TARGET_KEYS = {
    "reported",
    "reported_value",
    "reported_values",
    "expected",
    "expected_value",
    "expected_values",
    "target_value",
    "target_values",
    "paper_result",
    "paper_results",
}


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_real_reproduction_case_packets_are_answer_free_and_fail_closed() -> None:
    packets = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(_CASES.glob("*.json"))]

    assert packets
    for packet in packets:
        assert _FORBIDDEN_TARGET_KEYS.isdisjoint(_keys(packet))
        assert packet["agent_independence_scoring"] != "eligible"
        gates = packet["readiness_gates"]
        if not all(gates.values()):
            assert packet["status"] == "not_ready_for_execution"
            assert packet["authority"]["production_authorized"] is False
            assert packet["authority"]["e4_authorized"] is False


def test_rugged_landscape_packet_does_not_misclassify_repository_listing_as_artifact_identity() -> None:
    packet = json.loads(
        (_CASES / "aejmic_2026_rugged_landscape_v0.11.json").read_text(encoding="utf-8")
    )

    package = packet["replication_package"]
    author_track = packet["execution_tracks"]["author_package"]
    independent = packet["execution_tracks"]["independent_reimplementation"]

    assert package["version"] == "V1"
    assert package["artifact_ingestion_status"] == "blocked_pending_artifact_level_terms_review"
    assert package["inventory_evidence_status"] == "repository_listing_only_not_artifact_hashes"
    assert author_track["source_artifact_sha256"] == []
    assert author_track["reference_output_sha256"] == []
    assert independent["author_code_visible"] is False
    assert independent["author_output_visible"] is False
    assert independent["network_allowed"] is False
    assert packet["target_contract"]["target_commitment_sha256"] is None


def test_model_lb_packet_pins_the_public_preprint_to_v1_3_1_not_latest() -> None:
    packet = json.loads(
        (_CASES / "ssrn_7138278_model_lb_v1.3.1_v0.11.json").read_text(encoding="utf-8")
    )

    package = packet["replication_package"]
    author_track = packet["execution_tracks"]["author_package"]
    independent = packet["execution_tracks"]["independent_reimplementation"]
    target = packet["target_contract"]
    drift = packet["version_drift_control"]

    assert package["release"] == "v1.3.1"
    assert package["git_commit_sha"] == "4ea6e5e4c9cf2088aa76f406705f5620e561e199"
    assert package["code_license"] == "MIT"
    assert package["local_sandbox_execution_authorized"] is True
    assert package["remote_model_egress_authorized"] is False
    assert author_track["network_allowed_during_execution"] is False
    assert author_track["source_mount_read_only"] is True
    assert author_track["credentials_mounted"] is False
    assert independent["author_code_visible"] is False
    assert independent["author_output_visible"] is False
    assert target["target_commitment_sha256"] is not None
    assert target["reported_numeric_value_stored_in_repository"] is False
    assert drift["later_release_observed"] == "v2.0.1"
    assert drift["later_release_must_not_replace_v1_3_1_for_this_target"] is True
