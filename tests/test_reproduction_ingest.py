from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import ReproductionTarget, target_commitment_sha256
from veritas.reproduction_ingest import (
    build_answer_free_reproduction_certificate,
    load_private_reproduction_target,
)
from veritas.types import Materiality

SOURCE_SHA = "1" * 64
ENV_SHA = "2" * 64
LOCK_SHA = "3" * 64
COMMIT_SHA = "4" * 40
BASE_IMAGE = "python:3.12-slim@sha256:" + "5" * 64


def _target(value: float = 0.049) -> ReproductionTarget:
    return ReproductionTarget(
        target_id="cad-p",
        claim_id="claim-cad",
        metric="p_value",
        reported=ReportedNumber(value, decimals=3),
        source=SourceLocation(artifact_id="paper", section="Abstract"),
        materiality=Materiality.MAIN_EMPIRICAL_CLAIM,
    )


def _write_output(tmp_path: Path, value: str = "0.0495") -> tuple[Path, str]:
    path = tmp_path / "ppp.csv"
    path.write_text(f"currency,pvalue_cf\nAUD,0.5\nCAD,{value}\n", encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _write_text_output(tmp_path: Path, value: str = "0.0495") -> tuple[Path, str]:
    path = tmp_path / "ppp.txt"
    path.write_text(f"AUD p=0.5\nCAD p={value}\n", encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_output(tmp_path: Path, value: object = 0.0495) -> tuple[Path, str]:
    path = tmp_path / "ppp.json"
    path.write_text(json.dumps({"results": {"CAD": {"p_value": value}}}), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _packet(output_sha256: str, target: ReproductionTarget, *, binding: dict | None = None) -> dict:
    if binding is None:
        binding = {
            "format": "csv",
            "row_match": {"currency": "CAD"},
            "value_column": "pvalue_cf",
        }
    return {
        "case_id": "case-1",
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
        "target_contract": {
            "target_id": target.target_id,
            "claim_id": target.claim_id,
            "metric": target.metric,
            "target_commitment_sha256": target_commitment_sha256((target,)),
            "reproduced_value_binding": binding,
            "reviewer_a_complete": True,
            "reviewer_b_complete": False,
            "adjudication_complete": False,
        },
    }


def _execution(output_sha256: str, value: float = 0.0495) -> dict:
    return {
        "case_id": "case-1",
        "track": "author_package_frozen_environment_rerun",
        "external_git_commit_sha": COMMIT_SHA,
        "source_manifest_sha256": SOURCE_SHA,
        "environment_freeze_sha256": ENV_SHA,
        "environment_lock_sha256": LOCK_SHA,
        "base_image": BASE_IMAGE,
        "output_artifact_sha256": output_sha256,
        "target_id": "cad-p",
        "reproduced_value": value,
        "exit_code": 0,
        "network_disabled": True,
        "source_mount_read_only": True,
        "runtime_precommitted": True,
        "credentials_mounted": False,
        "veritas_repository_mounted": False,
    }


def test_answer_free_ingest_uses_existing_rounding_comparator(tmp_path: Path) -> None:
    target = _target()
    output, output_sha256 = _write_output(tmp_path)

    certificate = build_answer_free_reproduction_certificate(
        packet=_packet(output_sha256, target),
        execution=_execution(output_sha256),
        private_target=target,
        output_path=output,
    )

    assert certificate["comparison"]["decision"] == "MATCH"
    assert certificate["comparison"]["status"] == "MATCH"
    assert certificate["comparison"]["target_commitment_validated"] is True
    assert certificate["comparison"]["output_artifact_bound"] is True
    assert certificate["authority"]["production_authorized"] is False
    assert certificate["authority"]["e4_authorized"] is False
    rendered = json.dumps(certificate, sort_keys=True)
    assert "0.049" not in rendered
    assert "0.0495" not in rendered


def test_answer_free_ingest_supports_hash_bound_text_regex_output(tmp_path: Path) -> None:
    target = _target()
    output, output_sha256 = _write_text_output(tmp_path)
    binding = {
        "format": "text_regex",
        "pattern": r"^CAD p=(?P<value>[0-9.]+)$",
    }

    certificate = build_answer_free_reproduction_certificate(
        packet=_packet(output_sha256, target, binding=binding),
        execution=_execution(output_sha256),
        private_target=target,
        output_path=output,
    )

    assert certificate["comparison"]["decision"] == "MATCH"
    assert certificate["comparison"]["output_artifact_bound"] is True


def test_answer_free_ingest_supports_strict_json_path_output(tmp_path: Path) -> None:
    target = _target()
    output, output_sha256 = _write_json_output(tmp_path)
    binding = {
        "format": "json_path",
        "path": ["results", "CAD", "p_value"],
    }

    certificate = build_answer_free_reproduction_certificate(
        packet=_packet(output_sha256, target, binding=binding),
        execution=_execution(output_sha256),
        private_target=target,
        output_path=output,
    )

    assert certificate["comparison"]["decision"] == "MATCH"
    assert certificate["comparison"]["status"] == "MATCH"
    rendered = json.dumps(certificate, sort_keys=True)
    assert "0.049" not in rendered
    assert "0.0495" not in rendered


def test_json_path_binding_supports_array_indices(tmp_path: Path) -> None:
    target = _target()
    output = tmp_path / "results.json"
    output.write_text(
        json.dumps({"targets": [{"target_id": "other", "value": 1.0}, {"target_id": "cad-p", "value": 0.0495}]}),
        encoding="utf-8",
    )
    output_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
    binding = {"format": "json_path", "path": ["targets", 1, "value"]}

    certificate = build_answer_free_reproduction_certificate(
        packet=_packet(output_sha256, target, binding=binding),
        execution=_execution(output_sha256),
        private_target=target,
        output_path=output,
    )

    assert certificate["comparison"]["decision"] == "MATCH"


def test_json_path_binding_rejects_missing_or_ambiguous_structure(tmp_path: Path) -> None:
    target = _target()
    output, output_sha256 = _write_json_output(tmp_path)
    packet = _packet(
        output_sha256,
        target,
        binding={"format": "json_path", "path": ["results", "USD", "p_value"]},
    )

    with pytest.raises(ValueError, match="did not resolve exactly"):
        build_answer_free_reproduction_certificate(
            packet=packet,
            execution=_execution(output_sha256),
            private_target=target,
            output_path=output,
        )


def test_json_path_binding_rejects_duplicate_object_keys(tmp_path: Path) -> None:
    target = _target()
    output = tmp_path / "duplicate.json"
    output.write_text('{"results":{"CAD":{"p_value":0.0495,"p_value":0.9}}}', encoding="utf-8")
    output_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
    packet = _packet(
        output_sha256,
        target,
        binding={"format": "json_path", "path": ["results", "CAD", "p_value"]},
    )

    with pytest.raises(ValueError, match="duplicate object keys"):
        build_answer_free_reproduction_certificate(
            packet=packet,
            execution=_execution(output_sha256),
            private_target=target,
            output_path=output,
        )


@pytest.mark.parametrize(
    "path,value,error,exception_type",
    [
        ([], 0.0495, "non-empty path", ValueError),
        (["results", -1], 0.0495, "non-negative", ValueError),
        (["results", 1.5], 0.0495, "object keys", TypeError),
        (["results", "CAD", "p_value"], True, "numeric scalar", TypeError),
    ],
)
def test_json_path_binding_rejects_unsafe_paths_and_values(
    tmp_path: Path,
    path: list[object],
    value: object,
    error: str,
    exception_type: type[Exception],
) -> None:
    target = _target()
    output, output_sha256 = _write_json_output(tmp_path, value=value)
    packet = _packet(output_sha256, target, binding={"format": "json_path", "path": path})

    with pytest.raises(exception_type, match=error):
        build_answer_free_reproduction_certificate(
            packet=packet,
            execution=_execution(output_sha256),
            private_target=target,
            output_path=output,
        )


def test_ingest_rejects_private_target_that_does_not_open_locked_commitment(tmp_path: Path) -> None:
    locked_target = _target()
    output, output_sha256 = _write_output(tmp_path)

    with pytest.raises(ValueError, match="target commitment"):
        build_answer_free_reproduction_certificate(
            packet=_packet(output_sha256, locked_target),
            execution=_execution(output_sha256),
            private_target=_target(0.20),
            output_path=output,
        )


def test_ingest_rejects_tampered_output_bytes(tmp_path: Path) -> None:
    target = _target()
    output, original_sha256 = _write_output(tmp_path)
    packet = _packet(original_sha256, target)
    execution = _execution(original_sha256)
    output.write_text("currency,pvalue_cf\nCAD,0.9\n", encoding="utf-8")

    with pytest.raises(ValueError, match="output artifact"):
        build_answer_free_reproduction_certificate(
            packet=packet,
            execution=execution,
            private_target=target,
            output_path=output,
        )


def test_ingest_rejects_attested_value_that_is_not_in_bound_output(tmp_path: Path) -> None:
    target = _target()
    output, output_sha256 = _write_output(tmp_path)

    with pytest.raises(ValueError, match="attestation value"):
        build_answer_free_reproduction_certificate(
            packet=_packet(output_sha256, target),
            execution=_execution(output_sha256, value=0.04),
            private_target=target,
            output_path=output,
        )


def test_private_target_loader_preserves_commitment_semantics(tmp_path: Path) -> None:
    target = _target()
    private_path = tmp_path / "private_target.json"
    private_path.write_text(
        json.dumps(
            {
                "target_id": target.target_id,
                "claim_id": target.claim_id,
                "metric": target.metric,
                "reported": {"value": 0.049, "decimals": 3, "operator": "="},
                "source": {"artifact_id": "paper", "section": "Abstract"},
                "materiality": int(Materiality.MAIN_EMPIRICAL_CLAIM),
            }
        ),
        encoding="utf-8",
    )

    loaded = load_private_reproduction_target(private_path)
    assert target_commitment_sha256((loaded,)) == target_commitment_sha256((target,))
