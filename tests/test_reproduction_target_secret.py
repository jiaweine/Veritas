from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas.reproduction_ingest import load_private_reproduction_target
from veritas.reproduction_ingest_set import load_private_reproduction_target_set
from veritas.types import Materiality


def _target_row() -> dict:
    return {
        "target_id": "beta",
        "claim_id": "claim-main",
        "metric": "coefficient",
        "reported": {"value": 0.125, "decimals": 3, "operator": "="},
        "source": {
            "artifact_id": "paper",
            "page": 4,
            "section": "Results",
            "table": "Table 2",
            "row": "Treatment",
            "column": "B",
            "char_start": 10,
            "char_end": 30,
            "bbox": [10.0, 20.0, 100.0, 40.0],
            "text_quote": "Treatment coefficient",
        },
        "materiality": int(Materiality.MAIN_EMPIRICAL_CLAIM),
    }


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_single_target_secret_accepts_explicit_v1_and_full_source(tmp_path: Path) -> None:
    payload = _target_row()
    payload["schema_version"] = 1
    path = tmp_path / "target.json"
    _write(path, payload)

    target = load_private_reproduction_target(path)

    assert target.target_id == "beta"
    assert target.reported.value == pytest.approx(0.125)
    assert target.reported.decimals == 3
    assert target.source.page == 4
    assert target.source.bbox == (10.0, 20.0, 100.0, 40.0)


def test_single_target_secret_preserves_legacy_unversioned_v1(tmp_path: Path) -> None:
    path = tmp_path / "target.json"
    _write(path, _target_row())
    assert load_private_reproduction_target(path).claim_id == "claim-main"


@pytest.mark.parametrize(
    ("mutator", "error"),
    [
        (lambda row: row.__setitem__("paper_answer", 0.125), "unexpected fields"),
        (lambda row: row["reported"].__setitem__("rounded_from", "table"), "unexpected fields"),
        (lambda row: row["source"].__setitem__("paper_url", "https://example.test"), "unexpected fields"),
    ],
)
def test_single_target_secret_rejects_unknown_channels(tmp_path: Path, mutator, error: str) -> None:
    payload = _target_row()
    mutator(payload)
    path = tmp_path / "target.json"
    _write(path, payload)

    with pytest.raises(ValueError, match=error):
        load_private_reproduction_target(path)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("target_id", "", "non-empty string"),
        ("claim_id", 7, "non-empty string"),
        ("metric", None, "non-empty string"),
        ("materiality", True, "must be an integer"),
    ],
)
def test_single_target_secret_rejects_invalid_identity_and_materiality(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    payload = _target_row()
    payload[field] = value
    path = tmp_path / "target.json"
    _write(path, payload)

    with pytest.raises((TypeError, ValueError), match=error):
        load_private_reproduction_target(path)


@pytest.mark.parametrize(
    ("value", "error"),
    [
        (True, "JSON number"),
        ("0.125", "JSON number"),
    ],
)
def test_single_target_secret_requires_reported_json_number(
    tmp_path: Path,
    value: object,
    error: str,
) -> None:
    payload = _target_row()
    payload["reported"]["value"] = value
    path = tmp_path / "target.json"
    _write(path, payload)

    with pytest.raises(TypeError, match=error):
        load_private_reproduction_target(path)


def test_single_target_secret_rejects_boolean_schema_version(tmp_path: Path) -> None:
    payload = _target_row()
    payload["schema_version"] = True
    path = tmp_path / "target.json"
    _write(path, payload)

    with pytest.raises(TypeError, match="schema_version.*integer"):
        load_private_reproduction_target(path)


def test_single_target_secret_rejects_invalid_decimals_and_source_ranges(tmp_path: Path) -> None:
    payload = _target_row()
    payload["reported"]["decimals"] = -1
    path = tmp_path / "target.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="decimals.*>= 0"):
        load_private_reproduction_target(path)

    payload = _target_row()
    payload["source"]["char_start"] = 30
    payload["source"]["char_end"] = 10
    _write(path, payload)
    with pytest.raises(ValueError, match="char_end"):
        load_private_reproduction_target(path)


def test_target_set_rows_use_same_exact_secret_schema(tmp_path: Path) -> None:
    first = _target_row()
    second = _target_row()
    second["target_id"] = "se"
    second["metric"] = "standard_error"
    second["reported"]["value"] = 0.04
    second["reported"]["decimals"] = 2
    path = tmp_path / "targets.json"
    _write(path, {"schema_version": 1, "targets": [first, second]})

    targets = load_private_reproduction_target_set(path)
    assert tuple(target.target_id for target in targets) == ("beta", "se")

    second["reported"]["secret_note"] = "do not accept undeclared fields"
    _write(path, {"schema_version": 1, "targets": [first, second]})
    with pytest.raises(ValueError, match="unexpected fields"):
        load_private_reproduction_target_set(path)


def test_target_set_rejects_row_level_schema_version(tmp_path: Path) -> None:
    row = _target_row()
    row["schema_version"] = 1
    path = tmp_path / "targets.json"
    _write(path, {"schema_version": 1, "targets": [row]})

    with pytest.raises(ValueError, match="unexpected fields"):
        load_private_reproduction_target_set(path)
