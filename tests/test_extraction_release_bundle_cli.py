from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_extraction_evidence_workflow import _workflow_fixture

from veritas.extraction_execution_evidence import extraction_prediction_artifact_bytes
from veritas.extraction_input_artifacts import (
    build_extraction_input_artifact_manifest,
    extraction_input_artifact_manifest_payload,
)
from veritas.extraction_release_archive import load_extraction_release_evidence_bundle
from veritas.extraction_review_record_json import extraction_review_record_json_payload


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fixture_args(tmp_path: Path):
    fixture = _workflow_fixture()
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    entries = []
    for paper in fixture["frame"].papers:
        relative = f"{paper.paper_id}.pdf"
        (input_root / relative).write_bytes(f"publication:{paper.paper_id}\n".encode())
        entries.append((paper.paper_id, relative))
    manifest = build_extraction_input_artifact_manifest(input_root, tuple(entries))
    manifest_path = tmp_path / "input-manifest.json"
    _write_json(manifest_path, extraction_input_artifact_manifest_payload(manifest))

    review_paths = []
    for record in fixture["review_records"]:
        path = tmp_path / "reviews" / f"{record.target.target_id}.json"
        _write_json(path, extraction_review_record_json_payload(record))
        review_paths.append(path)

    release_root = tmp_path / "release-artifacts"
    development_args = []
    for observation in fixture["observations"]:
        relative = f"development/{observation.threshold_id}.json"
        path = release_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(extraction_prediction_artifact_bytes(observation.predictions or ()))
        development_args.append(
            (
                observation.threshold_id,
                str(observation.threshold),
                f"development-{observation.threshold_id}",
                relative,
            )
        )
    test_args = []
    for observation in fixture["test_observations"]:
        relative = f"test/{observation.threshold_id}.json"
        path = release_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(extraction_prediction_artifact_bytes(observation.predictions or ()))
        test_args.append(
            (
                observation.threshold_id,
                str(observation.threshold),
                f"test-{observation.threshold_id}",
                relative,
            )
        )

    output = tmp_path / "release-bundle.json"
    args = [
        sys.executable,
        "scripts/build_extraction_release_bundle.py",
        "--release-artifact-root",
        str(release_root),
        "--input-artifact-manifest",
        str(manifest_path),
        "--input-artifact-root",
        str(input_root),
        "--min-selective-coverage",
        str(fixture["policy"].min_selective_coverage),
        "--min-accepted-full-accuracy",
        str(fixture["policy"].min_accepted_full_accuracy),
        "--max-critical-family-wrong-accept-upper-bound",
        str(fixture["policy"].max_critical_family_wrong_accept_upper_bound),
        "--output",
        str(output),
    ]
    for path in review_paths:
        args.extend(("--review-record", str(path)))
    for run in development_args:
        args.extend(("--development-run", *run))
    for run in test_args:
        args.extend(("--test-run", *run))
    return fixture, args, output, input_root, manifest_path, entries


def test_release_bundle_cli_builds_canonical_source_closed_archive(tmp_path: Path) -> None:
    fixture, args, output, _, _, _ = _fixture_args(tmp_path)

    result = subprocess.run(
        args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    bundle = load_extraction_release_evidence_bundle(output)
    assert len(bundle.review_records) == len(fixture["review_records"])
    assert len(bundle.development_runs) == len(fixture["observations"])
    assert len(bundle.test_runs) == len(fixture["test_observations"])
    assert bundle.threshold_policy == fixture["policy"]
    assert result.stdout.strip() == bundle.sha256()


def test_release_bundle_cli_rejects_review_source_outside_verified_manifest(
    tmp_path: Path,
) -> None:
    _, args, output, input_root, manifest_path, entries = _fixture_args(tmp_path)
    incomplete = build_extraction_input_artifact_manifest(input_root, tuple(entries[1:]))
    _write_json(manifest_path, extraction_input_artifact_manifest_payload(incomplete))

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "outside the verified input-artifact manifest" in result.stderr
    assert not output.exists()
