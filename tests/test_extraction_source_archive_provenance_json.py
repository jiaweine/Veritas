from __future__ import annotations

import json

import pytest
from test_extraction_source_archive_provenance import _source_archive_fixture

from veritas.extraction_source_archive_provenance_json import (
    extraction_signed_source_archive_provenance_json_payload,
    extraction_source_archive_trust_policy_json_payload,
    load_extraction_signed_source_archive_provenance,
    load_extraction_source_archive_trust_policy,
)


def test_source_archive_policy_json_round_trips_strictly(tmp_path) -> None:
    policy, _, _, _ = _source_archive_fixture()
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            extraction_source_archive_trust_policy_json_payload(policy),
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    assert load_extraction_source_archive_trust_policy(path) == policy


def test_signed_source_archive_provenance_json_round_trips_strictly(tmp_path) -> None:
    _, _, _, signed = _source_archive_fixture()
    path = tmp_path / "signed.json"
    path.write_text(
        json.dumps(
            extraction_signed_source_archive_provenance_json_payload(signed),
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    assert load_extraction_signed_source_archive_provenance(path) == signed


def test_source_archive_policy_json_rejects_unknown_keys(tmp_path) -> None:
    policy, _, _, _ = _source_archive_fixture()
    payload = extraction_source_archive_trust_policy_json_payload(policy)
    payload["unexpected"] = True
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="keys differ from schema"):
        load_extraction_source_archive_trust_policy(path)


def test_source_archive_json_rejects_duplicate_keys(tmp_path) -> None:
    _, _, _, signed = _source_archive_fixture()
    payload = extraction_signed_source_archive_provenance_json_payload(signed)
    statement = json.dumps(payload["statement"], sort_keys=True)
    raw = (
        '{"algorithm":"ed25519","algorithm":"ed25519",'
        f'"schema_version":1,"signature_hex":"{signed.signature_hex}",'
        f'"statement":{statement}'
        "}"
    )
    path = tmp_path / "signed.json"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate object key"):
        load_extraction_signed_source_archive_provenance(path)


def test_source_archive_json_rejects_nonstandard_numbers(tmp_path) -> None:
    _, _, _, signed = _source_archive_fixture()
    payload = extraction_signed_source_archive_provenance_json_payload(signed)
    payload["statement"]["run_attempt"] = float("nan")
    path = tmp_path / "signed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="non-standard JSON numeric constant"):
        load_extraction_signed_source_archive_provenance(path)
