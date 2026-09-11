from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_extraction_evidence_workflow import _workflow_fixture

from veritas.extraction_evidence_plan_json import (
    extraction_evidence_plan_json_payload,
    load_extraction_evidence_plan,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_evidence_plan_strict_json_round_trip(tmp_path: Path) -> None:
    fixture = _workflow_fixture()
    plan = fixture["plan"]
    grid = fixture["grid"]
    path = tmp_path / "evidence-plan.json"
    _write_json(path, extraction_evidence_plan_json_payload(plan, grid))

    loaded_plan, loaded_grid = load_extraction_evidence_plan(path)

    assert loaded_plan == plan
    assert loaded_grid == grid
    assert loaded_plan.sha256() == plan.sha256()
    assert loaded_grid.sha256() == grid.sha256()


def test_evidence_plan_loader_rejects_payload_hash_drift(tmp_path: Path) -> None:
    fixture = _workflow_fixture()
    payload = extraction_evidence_plan_json_payload(fixture["plan"], fixture["grid"])
    payload["plan"]["split_salt"] = "post-hoc-salt"
    path = tmp_path / "drifted-plan.json"
    _write_json(path, payload)

    with pytest.raises(ValueError, match="does not match archived plan_sha256"):
        load_extraction_evidence_plan(path)


def test_evidence_plan_loader_rejects_grid_drift_and_unknown_keys(tmp_path: Path) -> None:
    fixture = _workflow_fixture()
    payload = extraction_evidence_plan_json_payload(fixture["plan"], fixture["grid"])
    payload["threshold_grid"][0]["threshold"] = 99.0
    path = tmp_path / "drifted-grid.json"
    _write_json(path, payload)

    with pytest.raises(ValueError, match="threshold grid does not match plan commitment"):
        load_extraction_evidence_plan(path)

    payload = extraction_evidence_plan_json_payload(fixture["plan"], fixture["grid"])
    payload["unexpected"] = True
    unknown = tmp_path / "unknown.json"
    _write_json(unknown, payload)
    with pytest.raises(ValueError, match="unknown=.*unexpected"):
        load_extraction_evidence_plan(unknown)


def test_evidence_plan_loader_rejects_duplicate_keys_and_nonproduction_drift(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate object key"):
        load_extraction_evidence_plan(duplicate)

    fixture = _workflow_fixture()
    payload = extraction_evidence_plan_json_payload(fixture["plan"], fixture["grid"])
    payload["production_authorized"] = True
    production = tmp_path / "production.json"
    _write_json(production, payload)
    with pytest.raises(ValueError, match="non-production"):
        load_extraction_evidence_plan(production)
