from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from veritas.benchmark import BenchmarkSplit
from veritas.extraction_calibration import lock_test_evaluation
from veritas.extraction_calibration_archive import (
    ExtractionTestEvaluationArchive,
    load_development_calibration_freeze,
    load_test_evaluation_archive,
    test_evaluation_archive_json_payload,
)
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bind an already frozen DEVELOPMENT-selected threshold to the exact TEST target "
            "manifest before TEST predictions are inspected. This command accepts no TEST "
            "prediction artifacts or TEST performance values."
        )
    )
    parser.add_argument("--development-freeze", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--test-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    freeze = load_development_calibration_freeze(args.development_freeze)
    development_manifest = load_extraction_split_target_manifest(args.development_manifest)
    test_manifest = load_extraction_split_target_manifest(args.test_manifest)

    if development_manifest.split is not BenchmarkSplit.DEVELOPMENT:
        raise ValueError("development manifest must use the DEVELOPMENT split")
    if test_manifest.split is not BenchmarkSplit.TEST:
        raise ValueError("test manifest must use the TEST split")
    if development_manifest.sha256() != freeze.development_manifest_sha256:
        raise ValueError("DEVELOPMENT manifest differs from the calibration freeze")
    if development_manifest.gold_manifest_sha256 != test_manifest.gold_manifest_sha256:
        raise ValueError("DEVELOPMENT and TEST manifests use different reviewed gold")
    if development_manifest.split_lock_sha256 != test_manifest.split_lock_sha256:
        raise ValueError("DEVELOPMENT and TEST manifests use different article-family split locks")

    development_families = set(development_manifest.article_family_ids)
    test_families = set(test_manifest.article_family_ids)
    overlap_families = tuple(sorted(development_families & test_families))
    if overlap_families:
        raise ValueError(
            "DEVELOPMENT and TEST article-family membership overlaps: "
            f"{overlap_families!r}"
        )
    development_targets = set(development_manifest.target_ids)
    test_targets = set(test_manifest.target_ids)
    overlap_targets = tuple(sorted(development_targets & test_targets))
    if overlap_targets:
        raise ValueError(
            "DEVELOPMENT and TEST target membership overlaps: "
            f"{overlap_targets!r}"
        )

    lock = lock_test_evaluation(
        freeze.frozen_threshold,
        test_manifest_sha256=test_manifest.sha256(),
    )
    archive = ExtractionTestEvaluationArchive(
        development_calibration_freeze_sha256=freeze.sha256(),
        development_calibration_freeze_file_sha256=_file_sha256(args.development_freeze),
        frozen_threshold_sha256=freeze.frozen_threshold.sha256(),
        test_manifest_sha256=test_manifest.sha256(),
        test_manifest_file_sha256=_file_sha256(args.test_manifest),
        test_evaluation_lock=lock,
    )

    payload = test_evaluation_archive_json_payload(archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reloaded = load_test_evaluation_archive(args.output)
    if reloaded != archive:
        raise ValueError("written TEST evaluation archive does not round-trip exactly")

    print(
        json.dumps(
            {
                "schema_version": 1,
                "production_authorized": False,
                "development_calibration_freeze_sha256": freeze.sha256(),
                "development_calibration_freeze_file_sha256": _file_sha256(
                    args.development_freeze
                ),
                "frozen_threshold_sha256": freeze.frozen_threshold.sha256(),
                "selected_threshold_id": freeze.frozen_threshold.threshold_id,
                "selected_threshold": freeze.frozen_threshold.threshold,
                "test_manifest_sha256": test_manifest.sha256(),
                "test_manifest_file_sha256": _file_sha256(args.test_manifest),
                "test_evaluation_lock_sha256": lock.sha256(),
                "test_evaluation_archive_sha256": archive.sha256(),
                "test_evaluation_archive_file_sha256": _file_sha256(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
