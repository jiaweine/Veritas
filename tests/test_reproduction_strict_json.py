from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas.reproduction_ingest import (
    build_answer_free_certificate_from_files,
    load_private_reproduction_target,
)
from veritas.reproduction_ingest_set import (
    build_answer_free_target_set_certificate_from_files,
    load_private_reproduction_target_set,
)
from veritas.reproduction_json import loads_strict_reproduction_json


def test_strict_reproduction_json_rejects_duplicate_object_keys() -> None:
    with pytest.raises(ValueError, match="duplicate object keys"):
        loads_strict_reproduction_json('{"case_id":"a","case_id":"b"}')


def test_strict_reproduction_json_rejects_nonstandard_numeric_constants() -> None:
    for value in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError, match="unsupported numeric constant"):
            loads_strict_reproduction_json(f'{{"value":{value}}}')


def test_single_private_target_rejects_nonfinite_numeric_string(tmp_path: Path) -> None:
    path = tmp_path / "private_target.json"
    path.write_text(
        json.dumps(
            {
                "target_id": "t1",
                "claim_id": "c1",
                "metric": "coefficient",
                "reported": {"value": "Infinity", "decimals": 2, "operator": "="},
                "source": {"artifact_id": "paper"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="private target reported value must be finite"):
        load_private_reproduction_target(path)


def test_target_set_private_targets_reject_nonfinite_numeric_string(tmp_path: Path) -> None:
    path = tmp_path / "private_targets.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "targets": [
                    {
                        "target_id": "t1",
                        "claim_id": "c1",
                        "metric": "coefficient",
                        "reported": {"value": "-Infinity", "decimals": 2, "operator": "="},
                        "source": {"artifact_id": "paper"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="private target reported value must be finite"):
        load_private_reproduction_target_set(path)


def test_single_target_file_ingest_rejects_ambiguous_packet_before_other_inputs(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    packet.write_text('{"case_id":"a","case_id":"b"}', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate object keys"):
        build_answer_free_certificate_from_files(
            packet_path=packet,
            execution_path=tmp_path / "missing-execution.json",
            private_target_path=tmp_path / "missing-target.json",
            output_path=tmp_path / "missing-output.json",
        )


def test_single_target_file_ingest_rejects_ambiguous_execution_before_secret(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    packet.write_text("{}", encoding="utf-8")
    execution = tmp_path / "execution.json"
    execution.write_text('{"case_id":"a","case_id":"b"}', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate object keys"):
        build_answer_free_certificate_from_files(
            packet_path=packet,
            execution_path=execution,
            private_target_path=tmp_path / "missing-target.json",
            output_path=tmp_path / "missing-output.json",
        )


def test_target_set_file_ingest_rejects_ambiguous_packet_before_other_inputs(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    packet.write_text('{"case_id":"a","case_id":"b"}', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate object keys"):
        build_answer_free_target_set_certificate_from_files(
            packet_path=packet,
            execution_path=tmp_path / "missing-execution.json",
            private_targets_path=tmp_path / "missing-targets.json",
            output_path=tmp_path / "missing-output.json",
        )


def test_target_set_file_ingest_rejects_ambiguous_execution_before_secret(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    packet.write_text("{}", encoding="utf-8")
    execution = tmp_path / "execution.json"
    execution.write_text('{"case_id":"a","case_id":"b"}', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate object keys"):
        build_answer_free_target_set_certificate_from_files(
            packet_path=packet,
            execution_path=execution,
            private_targets_path=tmp_path / "missing-targets.json",
            output_path=tmp_path / "missing-output.json",
        )
