from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_extraction_evidence_workflow import _workflow_fixture

from veritas.extraction_calibration import ExtractionThresholdPolicy
from veritas.extraction_release_archive import (
    ExtractionArchivedThresholdRun,
    ExtractionReleaseEvidenceBundle,
    extraction_release_evidence_bundle_payload,
)
from veritas.extraction_review_record_json import (
    extraction_review_record_json_payload,
    load_extraction_review_record,
)


def _write(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_review_record_archive_round_trips_and_matches_bundle_schema(tmp_path: Path) -> None:
    record = _workflow_fixture()["review_records"][0]
    payload = extraction_review_record_json_payload(record)
    path = tmp_path / "review-record.json"
    _write(path, payload)

    assert load_extraction_review_record(path) == record

    bundle = ExtractionReleaseEvidenceBundle(
        review_records=(record,),
        threshold_policy=ExtractionThresholdPolicy(
            min_selective_coverage=0.0,
            min_accepted_full_accuracy=0.0,
            max_critical_family_wrong_accept_upper_bound=1.0,
        ),
        development_runs=(
            ExtractionArchivedThresholdRun("t-1", 0.1, "dev-t-1", "dev/t-1.json"),
        ),
        test_runs=(
            ExtractionArchivedThresholdRun("t-1", 0.1, "test-t-1", "test/t-1.json"),
        ),
    )
    assert extraction_release_evidence_bundle_payload(bundle)["review_records"][0] == payload


def test_review_record_archive_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    record = _workflow_fixture()["review_records"][0]
    text = json.dumps(extraction_review_record_json_payload(record), sort_keys=True)
    text = text.replace(
        '"schema_version": 1,',
        '"schema_version": 1, "schema_version": 1,',
        1,
    )
    path = tmp_path / "duplicate.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON object key"):
        load_extraction_review_record(path)


def test_review_record_archive_rejects_typed_security_drift(tmp_path: Path) -> None:
    record = _workflow_fixture()["review_records"][0]
    payload = extraction_review_record_json_payload(record)
    payload["target"]["critical_for_hard_audit"] = "true"
    path = tmp_path / "typed-drift.json"
    _write(path, payload)

    with pytest.raises(TypeError, match="critical_for_hard_audit"):
        load_extraction_review_record(path)
