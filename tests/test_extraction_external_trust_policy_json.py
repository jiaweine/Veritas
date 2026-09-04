from __future__ import annotations

import json

import pytest
from test_extraction_external_trust_policy import _policy_fixture

from veritas.extraction_external_trust_policy_json import (
    extraction_external_trust_policy_json_payload,
    load_extraction_external_trust_policy,
)


def test_external_trust_policy_round_trip(tmp_path) -> None:
    policy, *_ = _policy_fixture()
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(extraction_external_trust_policy_json_payload(policy)),
        encoding="utf-8",
    )
    assert load_extraction_external_trust_policy(path) == policy


def test_external_trust_policy_rejects_duplicate_keys(tmp_path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate object key"):
        load_extraction_external_trust_policy(path)


def test_external_trust_policy_rejects_unknown_fields(tmp_path) -> None:
    policy, *_ = _policy_fixture()
    payload = extraction_external_trust_policy_json_payload(policy)
    payload["unexpected"] = "value"
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown=.*unexpected"):
        load_extraction_external_trust_policy(path)


def test_external_trust_policy_rejects_non_utf8(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8 JSON"):
        load_extraction_external_trust_policy(path)


def test_external_trust_policy_rejects_nonstandard_numeric_constant(tmp_path) -> None:
    policy, *_ = _policy_fixture()
    payload = extraction_external_trust_policy_json_payload(policy)
    text = json.dumps(payload).replace('"schema_version": 1', '"schema_version": NaN')
    path = tmp_path / "nan.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="non-standard JSON numeric constant"):
        load_extraction_external_trust_policy(path)
