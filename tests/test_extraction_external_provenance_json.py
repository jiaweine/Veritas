from __future__ import annotations

import json

import pytest
from test_extraction_external_provenance import _signed_fixture

from veritas.extraction_external_provenance_json import (
    extraction_external_trust_root_payload,
    extraction_signed_external_provenance_payload,
    load_extraction_external_trust_root,
    load_extraction_signed_external_provenance,
)


def test_external_trust_root_and_signed_provenance_round_trip(tmp_path) -> None:
    trust_root, _, _, signed = _signed_fixture()
    root_path = tmp_path / "trust-root.json"
    signed_path = tmp_path / "signed-provenance.json"
    root_path.write_text(
        json.dumps(extraction_external_trust_root_payload(trust_root)),
        encoding="utf-8",
    )
    signed_path.write_text(
        json.dumps(extraction_signed_external_provenance_payload(signed)),
        encoding="utf-8",
    )

    assert load_extraction_external_trust_root(root_path) == trust_root
    assert load_extraction_signed_external_provenance(signed_path) == signed


def test_external_provenance_json_rejects_duplicate_keys(tmp_path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,"issuer":"x"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate object key"):
        load_extraction_external_trust_root(path)


def test_external_provenance_json_rejects_unknown_statement_fields(tmp_path) -> None:
    _, _, _, signed = _signed_fixture()
    payload = extraction_signed_external_provenance_payload(signed)
    payload["statement"]["unexpected"] = "value"
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown=.*unexpected"):
        load_extraction_signed_external_provenance(path)


def test_external_provenance_json_rejects_nonstandard_numeric_constants(tmp_path) -> None:
    _, _, _, signed = _signed_fixture()
    payload = extraction_signed_external_provenance_payload(signed)
    text = json.dumps(payload).replace('"run_attempt": 1', '"run_attempt": NaN')
    path = tmp_path / "nan.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="non-standard JSON numeric constant"):
        load_extraction_signed_external_provenance(path)


def test_external_provenance_json_rejects_non_utf8_bytes(tmp_path) -> None:
    path = tmp_path / "invalid-utf8.json"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8 JSON"):
        load_extraction_external_trust_root(path)
