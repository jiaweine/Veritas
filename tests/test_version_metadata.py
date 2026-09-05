from __future__ import annotations

import tomllib
from pathlib import Path

import veritas


def test_package_metadata_version_matches_runtime_version() -> None:
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["version"] == veritas.__version__
    assert veritas.__version__ == "0.14.0"


def test_extraction_evidence_workflow_is_exported_from_package_root() -> None:
    expected = {
        "ExtractionEvidencePlan",
        "ExtractionEvidenceReleaseReceipt",
        "ExtractionSamplingFrame",
        "ExtractionSeedManifest",
        "ExtractionSplitTargetManifest",
        "ExtractionThresholdGrid",
        "build_extraction_benchmark_report_from_outcomes",
        "build_extraction_evidence_plan",
        "build_extraction_evidence_release_receipt",
        "build_extraction_gold_manifest",
        "build_extraction_split_target_manifest",
        "extraction_evidence_plan_payload",
        "file_sha256",
        "load_extraction_sampling_frame",
        "load_extraction_seed_manifest",
        "validate_extraction_benchmark_report",
        "validate_extraction_gold_review_records",
    }

    assert expected <= set(veritas.__all__)
    for name in expected:
        assert getattr(veritas, name) is not None