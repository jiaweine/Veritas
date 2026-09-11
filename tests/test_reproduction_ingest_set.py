from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import ReproductionTarget, target_commitment_sha256
from veritas.reproduction_ingest_set import (
    build_answer_free_reproduction_target_set_certificate,
    load_private_reproduction_target_set,
)
from veritas.types import Materiality

SOURCE_SHA = "1" * 64
ENV_SHA = "2" * 64
LOCK_SHA = "3" * 64
COMMIT_SHA = "4" * 40
BASE_IMAGE = "python:3.12-slim@sha256:" + "5" * 64


def _targets() -> tuple[ReproductionTarget, ReproductionTarget]:
    return (
        ReproductionTarget(
            target_id="cad-p",
            claim_id="claim-cad",
            metric="p_value",
            reported=ReportedNumber(0.049, decimals=3),
            source=SourceLocation(artifact_id="paper", section="Abstract"),
            materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
        ReproductionTarget(
            target_id="cad-beta",
            claim_id="claim-cad",
            metric="coefficient",
            reported=ReportedNumber(1.23, decimals=2),
            source=SourceLocation(artifact_id="paper", table="2", row="CAD"),
            materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
        ),
    )


def _write_output(
    tmp_path: Path,
    rows: list[dict[str, object]],
) -> tuple[Path, str]:
    path = tmp_path / "reproduction_results.json"
    path.write_text(json.dumps({"schema_version": 1, "targets": rows}), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _packet(output_sha256: str, targets: tuple[ReproductionTarget, ...]) -> dict:
    return {
        "case_id": "case-set-1",
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
        "target_set_contract": {
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
        },
    }


def _execution(output_sha256: str, targets: tuple[ReproductionTarget, ...]) -> dict:
    return {
        "case_id": "case-set-1",
        "track": "author_package_frozen_environment_rerun",
        "external_git_commit_sha": COMMIT_SHA,
        "source_manifest_sha256": SOURCE_SHA,
        "environment_freeze_sha256": ENV_SHA,
        "environment_lock_sha256": LOCK_SHA,
        "base_image": BASE_IMAGE,
        "output_artifact_sha256": output_sha256,
        "target_ids": [target.target_id for target in targets],
        "exit_code": 0,
        "network_disabled": True,
        "source_mount_read_only": True,
        "runtime_precommitted": True,
        "credentials_mounted": False,
        "veritas_repository_mounted": False,
    }


def test_target_set_ingest_matches_multiple_cells_without_persisting_values(tmp_path: Path) -> None:
    targets = _targets()
    output, output_sha256 = _write_output(
        tmp_path,
        [
            {"target_id": "cad-p", "value": 0.0495},
            {"target_id": "cad-beta", "value": 1.234},
        ],
    )

    certificate = build_answer_free_reproduction_target_set_certificate(
        packet=_packet(output_sha256, targets),
        execution=_execution(output_sha256, targets),
        private_targets=targets,
        output_path=output,
    )

    assert certificate["comparison"]["decision"] == "MATCH"
    assert certificate["comparison"]["matched_targets"] == 2
    assert certificate["comparison"]["missing_targets"] == 0
    assert certificate["claims"] == [
        {
            "claim_id": "claim-cad",
            "decision": "MATCH",
            "targets": [
                {
                    "target_id": "cad-p",
                    "metric": "p_value",
                    "status": "MATCH",
                    "output_artifact_bound": True,
                },
                {
                    "target_id": "cad-beta",
                    "metric": "coefficient",
                    "status": "MATCH",
                    "output_artifact_bound": True,
                },
            ],
        }
    ]
    assert certificate["authority"]["production_authorized"] is False
    assert certificate["authority"]["e4_authorized"] is False
    rendered = json.dumps(certificate, sort_keys=True)
    for secret in ("0.049", "0.0495", "1.23", "1.234"):
        assert secret not in rendered


def test_target_set_ingest_reports_partial_when_one_sealed_cell_is_missing(tmp_path: Path) -> None:
    targets = _targets()
    output, output_sha256 = _write_output(
        tmp_path,
        [{"target_id": "cad-p", "value": 0.0495}],
    )

    certificate = build_answer_free_reproduction_target_set_certificate(
        packet=_packet(output_sha256, targets),
        execution=_execution(output_sha256, targets),
        private_targets=targets,
        output_path=output,
    )

    assert certificate["comparison"]["decision"] == "PARTIAL"
    assert certificate["comparison"]["matched_targets"] == 1
    assert certificate["comparison"]["missing_targets"] == 1
    assert certificate["claims"][0]["decision"] == "PARTIAL"
    assert certificate["claims"][0]["targets"][1]["status"] == "MISSING"


def test_target_set_ingest_reports_mismatch_without_promoting_authority(tmp_path: Path) -> None:
    targets = _targets()
    output, output_sha256 = _write_output(
        tmp_path,
        [
            {"target_id": "cad-p", "value": 0.0495},
            {"target_id": "cad-beta", "value": 9.0},
        ],
    )

    certificate = build_answer_free_reproduction_target_set_certificate(
        packet=_packet(output_sha256, targets),
        execution=_execution(output_sha256, targets),
        private_targets=targets,
        output_path=output,
    )

    assert certificate["comparison"]["decision"] == "MISMATCH"
    assert certificate["comparison"]["mismatched_targets"] == 1
    assert certificate["authority"]["max_evidence_grade"] == "WEAK_SIGNAL"
    assert certificate["authority"]["e4_authorized"] is False


def test_target_set_ingest_rejects_extra_or_duplicate_output_targets(tmp_path: Path) -> None:
    targets = _targets()
    extra_output, extra_sha256 = _write_output(
        tmp_path,
        [{"target_id": "usd-p", "value": 0.1}],
    )
    with pytest.raises(ValueError, match="unexpected target-set output target_id"):
        build_answer_free_reproduction_target_set_certificate(
            packet=_packet(extra_sha256, targets),
            execution=_execution(extra_sha256, targets),
            private_targets=targets,
            output_path=extra_output,
        )

    duplicate_output, duplicate_sha256 = _write_output(
        tmp_path,
        [
            {"target_id": "cad-p", "value": 0.0495},
            {"target_id": "cad-p", "value": 0.0495},
        ],
    )
    with pytest.raises(ValueError, match="duplicate target-set output target_id"):
        build_answer_free_reproduction_target_set_certificate(
            packet=_packet(duplicate_sha256, targets),
            execution=_execution(duplicate_sha256, targets),
            private_targets=targets,
            output_path=duplicate_output,
        )


def test_target_set_ingest_rejects_reordered_secret_or_execution_identity(tmp_path: Path) -> None:
    targets = _targets()
    output, output_sha256 = _write_output(
        tmp_path,
        [
            {"target_id": "cad-p", "value": 0.0495},
            {"target_id": "cad-beta", "value": 1.234},
        ],
    )
    packet = _packet(output_sha256, targets)

    with pytest.raises(ValueError, match="target-set commitment"):
        build_answer_free_reproduction_target_set_certificate(
            packet=packet,
            execution=_execution(output_sha256, targets),
            private_targets=tuple(reversed(targets)),
            output_path=output,
        )

    execution = _execution(output_sha256, targets)
    execution["target_ids"] = list(reversed(execution["target_ids"]))
    with pytest.raises(ValueError, match="execution target ids"):
        build_answer_free_reproduction_target_set_certificate(
            packet=packet,
            execution=execution,
            private_targets=targets,
            output_path=output,
        )


def test_target_set_ingest_rejects_numeric_attestation_side_channel(tmp_path: Path) -> None:
    targets = _targets()
    output, output_sha256 = _write_output(
        tmp_path,
        [{"target_id": "cad-p", "value": 0.0495}],
    )
    execution = _execution(output_sha256, targets)
    execution["reproduced_values"] = {"cad-p": 0.0495}

    with pytest.raises(ValueError, match="must not duplicate"):
        build_answer_free_reproduction_target_set_certificate(
            packet=_packet(output_sha256, targets),
            execution=execution,
            private_targets=targets,
            output_path=output,
        )


def test_private_target_set_loader_preserves_ordered_commitment(tmp_path: Path) -> None:
    targets = _targets()
    path = tmp_path / "private_targets.json"
    path.write_text(
        json.dumps(
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
                            "operator": target.reported.operator.value,
                        },
                        "source": {
                            "artifact_id": target.source.artifact_id,
                            "section": target.source.section,
                            "table": target.source.table,
                            "row": target.source.row,
                        },
                        "materiality": int(target.materiality),
                    }
                    for target in targets
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_private_reproduction_target_set(path)

    assert tuple(target.target_id for target in loaded) == ("cad-p", "cad-beta")
    assert target_commitment_sha256(loaded) == target_commitment_sha256(targets)
