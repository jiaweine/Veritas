from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_extraction_evidence_workflow import _workflow_fixture
from test_extraction_execution_evidence import _attested_release, _execution_plan

from veritas.extraction_execution_evidence import extraction_prediction_artifact_bytes
from veritas.extraction_release_archive import (
    ExtractionArchivedThresholdRun,
    ExtractionReleaseEvidenceBundle,
    extraction_release_evidence_bundle_payload,
    load_extraction_prediction_artifact,
    load_extraction_release_evidence_bundle,
    rebuild_attested_extraction_evidence_release_receipt_from_archive,
)


def _archive_fixture(tmp_path: Path):
    fixture = _workflow_fixture()
    artifact_root = tmp_path / "release-artifacts"
    artifact_root.mkdir()

    def write_runs(observations, split: str):
        runs = []
        split_root = artifact_root / split
        split_root.mkdir()
        for observation in observations:
            relative_path = f"{split}/{observation.threshold_id}.predictions.json"
            (artifact_root / relative_path).write_bytes(
                extraction_prediction_artifact_bytes(observation.predictions or ())
            )
            runs.append(
                ExtractionArchivedThresholdRun(
                    threshold_id=observation.threshold_id,
                    threshold=observation.threshold,
                    execution_id=f"{split}-{observation.threshold_id}",
                    prediction_artifact_path=relative_path,
                )
            )
        return tuple(runs)

    bundle = ExtractionReleaseEvidenceBundle(
        review_records=fixture["review_records"],
        threshold_policy=fixture["policy"],
        development_runs=write_runs(fixture["observations"], "development"),
        test_runs=write_runs(fixture["test_observations"], "test"),
    )
    bundle_path = tmp_path / "release-bundle.json"
    bundle_path.write_text(
        json.dumps(
            extraction_release_evidence_bundle_payload(bundle),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture, artifact_root, bundle, bundle_path


def test_release_bundle_round_trips_strict_json(tmp_path: Path) -> None:
    _, _, bundle, bundle_path = _archive_fixture(tmp_path)
    loaded = load_extraction_release_evidence_bundle(bundle_path)
    assert loaded == bundle
    assert loaded.production_authorized is False
    assert loaded.sha256() == bundle.sha256()


def test_cold_archive_rebuilds_exact_attested_release(tmp_path: Path) -> None:
    fixture, artifact_root, bundle, _ = _archive_fixture(tmp_path)
    execution_plan = _execution_plan()
    rebuilt = rebuild_attested_extraction_evidence_release_receipt_from_archive(
        bundle,
        release_artifact_root=artifact_root,
        plan=fixture["plan"],
        sampling_frame=fixture["frame"],
        seed_manifest=fixture["seed"],
        threshold_grid=fixture["grid"],
        execution_plan=execution_plan,
    )
    assert rebuilt == _attested_release(execution_plan=execution_plan)


def test_prediction_artifact_loader_requires_canonical_exact_bytes(tmp_path: Path) -> None:
    fixture, artifact_root, bundle, _ = _archive_fixture(tmp_path)
    run = bundle.development_runs[0]
    artifact_path = artifact_root / run.prediction_artifact_path
    predictions = load_extraction_prediction_artifact(artifact_path)
    assert predictions == fixture["observations"][0].predictions

    artifact_path.write_bytes(artifact_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="canonical JSON contract"):
        load_extraction_prediction_artifact(artifact_path)


def test_release_rebuild_rejects_prediction_artifact_byte_drift(tmp_path: Path) -> None:
    fixture, artifact_root, bundle, _ = _archive_fixture(tmp_path)
    run = bundle.test_runs[0]
    artifact_path = artifact_root / run.prediction_artifact_path
    artifact_path.write_bytes(artifact_path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="canonical JSON contract"):
        rebuild_attested_extraction_evidence_release_receipt_from_archive(
            bundle,
            release_artifact_root=artifact_root,
            plan=fixture["plan"],
            sampling_frame=fixture["frame"],
            seed_manifest=fixture["seed"],
            threshold_grid=fixture["grid"],
            execution_plan=_execution_plan(),
        )


def test_release_bundle_rejects_prediction_path_traversal() -> None:
    with pytest.raises(ValueError, match="safe POSIX relative path"):
        ExtractionArchivedThresholdRun(
            threshold_id="t-1",
            threshold=0.1,
            execution_id="dev-t-1",
            prediction_artifact_path="../predictions.json",
        )


def test_release_bundle_rejects_duplicate_prediction_paths(tmp_path: Path) -> None:
    fixture, _, bundle, _ = _archive_fixture(tmp_path)
    duplicate = ExtractionArchivedThresholdRun(
        threshold_id=bundle.test_runs[0].threshold_id,
        threshold=bundle.test_runs[0].threshold,
        execution_id=bundle.test_runs[0].execution_id,
        prediction_artifact_path=bundle.development_runs[0].prediction_artifact_path,
    )
    with pytest.raises(ValueError, match="prediction artifact paths must be unique"):
        ExtractionReleaseEvidenceBundle(
            review_records=fixture["review_records"],
            threshold_policy=fixture["policy"],
            development_runs=bundle.development_runs,
            test_runs=(duplicate, *bundle.test_runs[1:]),
        )
