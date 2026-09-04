from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.extraction_evidence_workflow import (
    ExtractionThresholdGrid,
    build_extraction_evidence_plan,
    extraction_evidence_plan_payload,
    load_extraction_sampling_frame,
)


def _threshold(value: str) -> tuple[str, float]:
    threshold_id, separator, raw_value = value.partition("=")
    if not separator or not threshold_id.strip() or not raw_value.strip():
        raise argparse.ArgumentTypeError("threshold must use ID=VALUE")
    try:
        numeric = float(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("threshold VALUE must be numeric") from exc
    return threshold_id, numeric


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a pre-TEST extraction evidence workflow commitment."
    )
    parser.add_argument(
        "--sampling-frame",
        type=Path,
        default=Path("benchmark/corpus/candidates.json"),
    )
    parser.add_argument("--split-salt", required=True)
    parser.add_argument(
        "--review-protocol-version",
        default="independent-double-review-v1",
    )
    parser.add_argument(
        "--threshold",
        action="append",
        type=_threshold,
        required=True,
        help="Precommit one threshold candidate as ID=VALUE; repeat for the full grid.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sampling_frame = load_extraction_sampling_frame(args.sampling_frame)
    threshold_grid = ExtractionThresholdGrid(points=tuple(args.threshold))
    plan = build_extraction_evidence_plan(
        sampling_frame,
        threshold_grid,
        review_protocol_version=args.review_protocol_version,
        split_salt=args.split_salt,
    )
    payload = extraction_evidence_plan_payload(plan, threshold_grid)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(plan.sha256())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
