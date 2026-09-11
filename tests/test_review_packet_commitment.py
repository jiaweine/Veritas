from __future__ import annotations

import json
from pathlib import Path

from veritas.extraction_evidence_workflow import load_extraction_seed_manifest
from veritas.extraction_review_packet import ExtractionReviewerPacket


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_v015_blinded_review_packet_hashes_rebuild_from_strict_seed() -> None:
    root = _root()
    seed = load_extraction_seed_manifest(
        root / "benchmark/extraction/evidence_seed_manifest_v0.15.json"
    )
    commitment = json.loads(
        (root / "benchmark/extraction/review_packet_commitment_v0.15.json").read_text(
            encoding="utf-8"
        )
    )

    assert commitment["status"] == "blinded_review_packet_bytes_archived_not_distributed"
    assert commitment["production_authorized"] is False
    assert commitment["seed_manifest_sha256"] == seed.source_manifest_sha256
    assert commitment["packet_bytes_archived_in_repository"] is False
    assert commitment["packet_bytes_archived_in_actions_artifact"] is True
    assert commitment["distributed_to_human_reviewers"] is False
    assert commitment["actual_reviewer_identities_assigned"] is False

    archive = commitment["packet_archive"]
    assert archive["workflow_run_id"] == 34055818804
    assert archive["run_attempt"] == 1
    assert archive["source_commit_sha"] == "f8ca5c62c7116a5ef6c266e4ccbaa66318552d9d"
    assert archive["artifact_id"] == 9995918459
    assert archive["artifact_name"] == (
        "v015-publication-inputs-and-review-packets-f8ca5c62c7116a5ef6c266e4ccbaa66318552d9d"
    )
    assert archive["artifact_digest"] == (
        "sha256:877375c126ac4e39537f9581c4311625f11c771560385e69c4b7094586bbda78"
    )
    assert archive["durable_independent_external_archive"] is False

    rows = commitment["reviewer_packets"]
    assert [row["reviewer_slot"] for row in rows] == ["reviewer-a", "reviewer-b"]
    assert all(row["target_count"] == len(seed.targets) == 18 for row in rows)
    assert {row["reviewer_slot"]: row["packet_file_sha256"] for row in rows} == {
        "reviewer-a": "1753c024b057d085ddc4af33e3d9a235f7481ebf996cd8271bdc760a1e513447",
        "reviewer-b": "113762ea38c1710d70217c743fc96ea3bcfa59bcf956cfbc6b80bfdf7bc95997",
    }

    rebuilt = {
        slot: ExtractionReviewerPacket(
            reviewer_slot=slot,
            seed_manifest_sha256=seed.source_manifest_sha256,
            targets=seed.targets,
        )
        for slot in ("reviewer-a", "reviewer-b")
    }
    assert {row["reviewer_slot"]: row["packet_sha256"] for row in rows} == {
        slot: packet.sha256() for slot, packet in rebuilt.items()
    }

    for packet in rebuilt.values():
        payload = packet.to_payload()
        assert payload["blinded_to_legacy_values"] is True
        assert payload["blinded_to_other_reviews"] is True
        assert all("accepted_normalized_values" not in target for target in payload["targets"])
        assert all("expected_fields" not in target for target in payload["targets"])
        assert payload["submission_template"]["accepted_normalized_values"] == [
            "<independently verified value>"
        ]

    note = commitment["note"]
    assert "No packet has been distributed to a human reviewer" in note
    assert "no reviewer identity has been assigned" in note
    assert "not a durable independent external historical archive" in note
