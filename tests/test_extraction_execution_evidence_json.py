from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_extraction_execution_evidence import _attested_release, _execution_plan

from veritas.extraction_execution_evidence_json import (
    attested_extraction_evidence_release_receipt_json_payload,
    extraction_execution_plan_json_payload,
    load_attested_extraction_evidence_release_receipt,
    load_extraction_execution_plan,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_execution_plan_strict_json_round_trip(tmp_path: Path) -> None:
    plan = _execution_plan()
    path = tmp_path / "execution-plan.json"
    _write_json(path, extraction_execution_plan_json_payload(plan))

    loaded = load_extraction_execution_plan(path)

    assert loaded == plan
    assert loaded.sha256() == plan.sha256()


def test_attested_release_strict_json_round_trip(tmp_path: Path) -> None:
    receipt = _attested_release()
    path = tmp_path / "attested-release.json"
    _write_json(path, attested_extraction_evidence_release_receipt_json_payload(receipt))

    loaded = load_attested_extraction_evidence_release_receipt(path)

    assert loaded == receipt
    assert loaded.evidence_plan_sha256 == receipt.evidence_plan_sha256
    assert loaded.sha256() == receipt.sha256()


def test_execution_evidence_json_rejects_unknown_and_duplicate_keys(tmp_path: Path) -> None:
    plan = _execution_plan()
    payload = extraction_execution_plan_json_payload(plan)
    payload["unexpected"] = "value"
    unknown = tmp_path / "unknown.json"
    _write_json(unknown, payload)

    with pytest.raises(ValueError, match="unknown=.*unexpected"):
        load_extraction_execution_plan(unknown)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":1,"schema_version":1}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate object key"):
        load_extraction_execution_plan(duplicate)


def test_execution_evidence_json_rejects_nonstandard_numbers_and_non_utf8(
    tmp_path: Path,
) -> None:
    receipt = _attested_release()
    payload = attested_extraction_evidence_release_receipt_json_payload(receipt)
    payload["schema_version"] = float("nan")
    nonstandard = tmp_path / "nan.json"
    _write_json(nonstandard, payload)

    with pytest.raises(ValueError, match="non-standard JSON numeric constant"):
        load_attested_extraction_evidence_release_receipt(nonstandard)

    non_utf8 = tmp_path / "non-utf8.json"
    non_utf8.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8 JSON"):
        load_attested_extraction_evidence_release_receipt(non_utf8)
