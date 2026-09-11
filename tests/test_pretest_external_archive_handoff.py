from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_v015_pretest_external_archive_handoff_closes_exact_repository_and_binary_inputs() -> None:
    root = _root()
    path = root / "benchmark/extraction/pretest_external_archive_handoff_v0.15.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert _sha256(path) == "90fe5c7e27b7a8133fad0d5ce485b7f6866383fa6ddf3155403c098aa4acb7fa"
    assert payload["schema_version"] == 1
    assert payload["status"] == (
        "repository_side_external_archive_handoff_ready_awaiting_independent_archive"
    )
    assert payload["production_authorized"] is False
    assert payload["executed_v015_development_or_test_predictions"] is False
    assert payload["pretest_witness"] == {
        "path": "benchmark/extraction/pretest_external_witness_commitment_v0.15.json",
        "sha256": "1f36c2ff4d27ddf82b099ee6ff1a3501a39cd98b554c17f59e7d2b1ebe4fc5d8",
    }
    assert payload["source_commit_sha"] == "d6ffdf7debd63281e0db5934e3d4b7ebafb98311"

    pending = payload["pending_external_evidence"]
    assert pending == {
        "external_trust_policy_built": False,
        "external_trust_root_pinned": False,
        "independent_archive_receipt_present": False,
        "source_archive_builder_history_preserved": False,
        "source_archive_provenance_statement_present": False,
        "source_archive_trust_policy_built": False,
    }

    requirements = payload["external_archive_requirements"]
    assert requirements == {
        "build_external_trust_policy_only_after_independent_root_selection": True,
        "do_not_copy_expected_context_from_future_signed_envelope": True,
        "immutable_or_append_only_record_required": True,
        "independently_controlled_historical_channel_required": True,
        "independently_select_expected_context_before_test": True,
        "pin_external_trust_root_before_test": True,
        "preserve_exact_bytes": True,
        "preserve_source_archive_builder_identity_and_history_for_commit_to_archive_claim": True,
        "record_external_timestamp_or_sequence_position": True,
    }

    repository_files = payload["repository_files"]
    assert len(repository_files) == 11
    assert [row["path"] for row in repository_files] == sorted(
        row["path"] for row in repository_files
    )
    for row in repository_files:
        repository_path = root / row["path"]
        assert repository_path.is_file()
        assert _sha256(repository_path) == row["sha256"]

    witness_path = root / payload["pretest_witness"]["path"]
    assert _sha256(witness_path) == payload["pretest_witness"]["sha256"]

    input_manifest = json.loads(
        (root / "benchmark/extraction/extraction_input_artifact_manifest_v0.15.json").read_text(
            encoding="utf-8"
        )
    )
    expected_publications = sorted(input_manifest["artifacts"], key=lambda row: row["artifact_id"])
    assert payload["required_external_binary_artifacts"]["publication_inputs"] == (
        expected_publications
    )

    review_commitment = json.loads(
        (root / "benchmark/extraction/review_packet_commitment_v0.15.json").read_text(
            encoding="utf-8"
        )
    )
    assert review_commitment["distributed_to_human_reviewers"] is False
    assert review_commitment["actual_reviewer_identities_assigned"] is False
    expected_packets = sorted(
        [
            {
                "reviewer_slot": row["reviewer_slot"],
                "packet_sha256": row["packet_sha256"],
                "packet_file_sha256": row["packet_file_sha256"],
                "target_count": row["target_count"],
            }
            for row in review_commitment["reviewer_packets"]
        ],
        key=lambda row: row["reviewer_slot"],
    )
    assert payload["required_external_binary_artifacts"]["blinded_reviewer_packets"] == (
        expected_packets
    )

    source_tree = payload["required_external_binary_artifacts"]["source_tree"]
    assert source_tree == {
        "archive_name": "source-tree-v0.15.tar",
        "sha256": "dbe998b2017aa616001d983df8f3c136d28f3dbd8c5183dcecc6bfcc9e1bd167",
    }
