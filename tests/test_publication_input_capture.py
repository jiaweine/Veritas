from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_input_artifacts import load_extraction_input_artifact_manifest


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_v015_publication_input_capture_closes_over_frozen_seed_and_manifest() -> None:
    root = _root()
    capture = json.loads(
        (root / "benchmark/extraction/publication_input_capture_v0.15.json").read_text(
            encoding="utf-8"
        )
    )
    plan = json.loads(
        (root / "benchmark/extraction/evidence_plan_v0.15.json").read_text(encoding="utf-8")
    )
    seed = json.loads(
        (root / "benchmark/extraction/evidence_seed_manifest_v0.15.json").read_text(
            encoding="utf-8"
        )
    )

    manifest_path = root / capture["input_manifest_path"]
    manifest_raw = manifest_path.read_bytes()
    manifest = load_extraction_input_artifact_manifest(manifest_path)

    assert capture["schema_version"] == 1
    assert capture["status"] == "captured_pretest_publication_bytes_in_github_actions_artifact"
    assert capture["production_authorized"] is False
    assert capture["evidence_plan_sha256"] == plan["plan_sha256"]
    assert sha256(manifest_raw).hexdigest() == capture["input_manifest_sha256"] == (
        "d318a546bdb9801d24a95db26c6ba4c44ed38a7262d3a31eccb728c89edf0f74"
    )
    assert manifest.production_authorized is False
    assert len(manifest.artifacts) == 4

    captured = {row["artifact_id"]: row for row in capture["publication_inputs"]}
    archived = {item.artifact_id: item for item in manifest.artifacts}
    assert captured.keys() == archived.keys()
    for artifact_id, item in archived.items():
        row = captured[artifact_id]
        assert row["relative_path"] == item.relative_path
        assert row["sha256"] == item.sha256
        assert row["size_bytes"] == item.size_bytes

    seed_urls = {case["pdf_url"] for case in seed["cases"]}
    capture_urls = {row["seed_pdf_url"] for row in capture["publication_inputs"]}
    assert capture_urls == seed_urls

    run = capture["capture"]
    assert run["repository"] == "jiaweine/Veritas"
    assert run["workflow_path"] == ".github/workflows/capture-v015-evidence-inputs.yml"
    assert run["workflow_run_id"] == 34055651252
    assert run["run_attempt"] == 1
    assert run["source_commit_sha"] == "ef73a9ca226a6bd6154f7375bb07fb485ef891c4"
    assert run["artifact_id"] == 9995869859
    assert run["artifact_name"] == (
        "v015-publication-inputs-ef73a9ca226a6bd6154f7375bb07fb485ef891c4"
    )
    assert sum(item.size_bytes for item in manifest.artifacts) == 13_772_158
    assert run["artifact_size_bytes"] > 0
    assert run["artifact_digest"].startswith("sha256:")
    assert len(run["artifact_digest"].removeprefix("sha256:")) == 64

    boundary = capture["authority_boundary"]
    assert "does not provide an independent external historical archive" in boundary
    assert "does not authorize production findings" in boundary
    assert "durable independent pre-TEST archive" in boundary
