from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_calibration_archive import (
    load_development_calibration_freeze,
    load_pretest_pilot_threshold_policy,
    load_test_evaluation_archive,
)
from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_release_archive import load_extraction_release_evidence_bundle
from veritas.extraction_release_calibration_binding import (
    load_extraction_release_calibration_binding,
    verify_extraction_release_calibration_binding,
)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that a release bundle is exactly bound to the frozen DEVELOPMENT calibration, "
            "TEST evaluation lock, precommitted pilot policy, split manifests, and release prediction "
            "bytes before running cold external-provenance verification."
        )
    )
    parser.add_argument("--release-bundle", type=Path, required=True)
    parser.add_argument("--release-calibration-binding", type=Path, required=True)
    parser.add_argument("--release-artifact-root", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
    parser.add_argument("--pilot-threshold-policy", type=Path, required=True)
    parser.add_argument("--development-freeze", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--test-evaluation-lock", type=Path, required=True)
    parser.add_argument("--test-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    bundle = load_extraction_release_evidence_bundle(args.release_bundle)
    binding = load_extraction_release_calibration_binding(args.release_calibration_binding)
    plan, threshold_grid = load_extraction_evidence_plan(args.evidence_plan)
    pilot_policy = load_pretest_pilot_threshold_policy(args.pilot_threshold_policy)
    development_freeze = load_development_calibration_freeze(args.development_freeze)
    development_manifest = load_extraction_split_target_manifest(args.development_manifest)
    test_evaluation_archive = load_test_evaluation_archive(args.test_evaluation_lock)
    test_manifest = load_extraction_split_target_manifest(args.test_manifest)

    verify_extraction_release_calibration_binding(
        binding,
        bundle=bundle,
        bundle_path=args.release_bundle,
        plan=plan,
        threshold_grid_sha256=threshold_grid.sha256(),
        pilot_policy=pilot_policy,
        pilot_policy_path=args.pilot_threshold_policy,
        development_freeze=development_freeze,
        development_freeze_path=args.development_freeze,
        development_manifest=development_manifest,
        development_manifest_path=args.development_manifest,
        test_evaluation_archive=test_evaluation_archive,
        test_evaluation_archive_path=args.test_evaluation_lock,
        test_manifest=test_manifest,
        test_manifest_path=args.test_manifest,
        release_artifact_root=args.release_artifact_root,
    )

    payload = {
        "schema_version": 1,
        "production_authorized": False,
        "release_bundle_sha256": bundle.sha256(),
        "release_calibration_binding_sha256": binding.sha256(),
        "release_calibration_binding_file_sha256": _file_sha256(
            args.release_calibration_binding
        ),
        "development_calibration_freeze_sha256": development_freeze.sha256(),
        "test_evaluation_archive_sha256": test_evaluation_archive.sha256(),
        "test_evaluation_lock_sha256": test_evaluation_archive.test_evaluation_lock.sha256(),
        "selected_threshold_id": development_freeze.frozen_threshold.threshold_id,
        "selected_threshold": development_freeze.frozen_threshold.threshold,
        "status": "release_calibration_binding_verified",
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
