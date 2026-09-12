from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_execution_evidence_json import load_extraction_execution_plan
from veritas.extraction_release_archive import load_extraction_release_evidence_bundle
from veritas.extraction_release_execution_binding import (
    load_extraction_release_execution_binding,
    verify_extraction_release_execution_binding,
)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _attestation_map(values: list[list[str]], *, label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for threshold_id, path_text in values:
        if threshold_id in result:
            raise ValueError(f"duplicate {label} attestation threshold id: {threshold_id!r}")
        result[threshold_id] = Path(path_text)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that release execution ids and prediction artifacts are exactly bound to the "
            "strict DEVELOPMENT/TEST execution-attestation archives and frozen execution plan."
        )
    )
    parser.add_argument("--release-bundle", type=Path, required=True)
    parser.add_argument("--release-execution-binding", type=Path, required=True)
    parser.add_argument("--release-artifact-root", type=Path, required=True)
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--test-manifest", type=Path, required=True)
    parser.add_argument(
        "--development-attestation",
        nargs=2,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "ATTESTATION_PATH"),
    )
    parser.add_argument(
        "--test-attestation",
        nargs=2,
        action="append",
        required=True,
        metavar=("THRESHOLD_ID", "ATTESTATION_PATH"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    bundle = load_extraction_release_evidence_bundle(args.release_bundle)
    binding = load_extraction_release_execution_binding(args.release_execution_binding)
    execution_plan = load_extraction_execution_plan(args.execution_plan)
    development_manifest = load_extraction_split_target_manifest(args.development_manifest)
    test_manifest = load_extraction_split_target_manifest(args.test_manifest)
    development_attestations = _attestation_map(
        args.development_attestation, label="DEVELOPMENT"
    )
    test_attestations = _attestation_map(args.test_attestation, label="TEST")

    verify_extraction_release_execution_binding(
        binding,
        bundle=bundle,
        bundle_path=args.release_bundle,
        execution_plan=execution_plan,
        execution_plan_path=args.execution_plan,
        development_manifest=development_manifest,
        test_manifest=test_manifest,
        release_artifact_root=args.release_artifact_root,
        development_attestation_paths=development_attestations,
        test_attestation_paths=test_attestations,
    )

    payload = {
        "schema_version": 1,
        "production_authorized": False,
        "status": "release_execution_binding_verified",
        "release_bundle_sha256": bundle.sha256(),
        "release_execution_binding_sha256": binding.sha256(),
        "release_execution_binding_file_sha256": _file_sha256(
            args.release_execution_binding
        ),
        "execution_plan_sha256": execution_plan.sha256(),
        "development_execution_ids": [
            item.execution_id for item in binding.development_attestations
        ],
        "test_execution_ids": [item.execution_id for item in binding.test_attestations],
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
