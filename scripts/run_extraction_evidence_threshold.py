from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from veritas.extraction_evidence_runner import run_extraction_evidence_threshold


def _paper_artifacts(values: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--paper-artifact values must use paper_id=artifact_id")
        paper_id, artifact_id = value.split("=", 1)
        if not paper_id.strip() or not artifact_id.strip():
            raise ValueError("--paper-artifact values must use non-empty paper_id=artifact_id")
        if paper_id in mapping:
            raise ValueError(f"duplicate --paper-artifact paper id: {paper_id!r}")
        mapping[paper_id] = artifact_id
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run one frozen extraction threshold against a blinded split target manifest using only "
            "byte-verified local publication artifacts. This command performs no network access and "
            "does not read the value-bearing seed manifest or reviewed gold."
        )
    )
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--input-artifact-root", type=Path, required=True)
    parser.add_argument("--review-packet", type=Path, required=True)
    parser.add_argument("--review-packet-sha256", required=True)
    parser.add_argument("--target-manifest", type=Path, required=True)
    parser.add_argument("--paper-artifact", action="append", required=True, default=[])
    parser.add_argument("--threshold-id", required=True)
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    run = run_extraction_evidence_threshold(
        input_artifact_manifest_path=args.input_artifact_manifest,
        input_artifact_root=args.input_artifact_root,
        review_packet_path=args.review_packet,
        expected_review_packet_sha256=args.review_packet_sha256,
        target_manifest_path=args.target_manifest,
        paper_artifacts=_paper_artifacts(args.paper_artifact),
        threshold_id=args.threshold_id,
        threshold=args.threshold,
        output_path=args.output,
    )
    payload = asdict(run)
    payload["split"] = run.split.value
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
