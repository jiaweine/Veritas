from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from veritas.extraction_evidence_workflow import (
    ExtractionThresholdGrid,
    build_extraction_evidence_plan,
    extraction_evidence_plan_payload,
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
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


def _confidence(value: str) -> float:
    try:
        numeric = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("benchmark confidence must be numeric") from exc
    if not math.isfinite(numeric) or not 0.0 < numeric < 1.0:
        raise argparse.ArgumentTypeError("benchmark confidence must be finite and in (0, 1)")
    return numeric


def _fraction(value: str) -> float:
    try:
        numeric = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("split fraction must be numeric") from exc
    if not math.isfinite(numeric) or numeric <= 0.0 or numeric >= 1.0:
        raise argparse.ArgumentTypeError("split fraction must be finite and in (0, 1)")
    return numeric


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a pre-TEST extraction evidence workflow commitment."
    )
    parser.add_argument(
        "--sampling-frame",
        type=Path,
        default=Path("benchmark/corpus/candidates.json"),
    )
    parser.add_argument(
        "--seed-manifest",
        type=Path,
        required=True,
        help="Exact reviewed-target seed manifest to precommit; never inferred from a legacy default.",
    )
    parser.add_argument("--split-salt", required=True)
    parser.add_argument(
        "--train-fraction",
        type=_fraction,
        default=0.60,
        help="Article-family TRAIN fraction to precommit before reviewed split assignment.",
    )
    parser.add_argument(
        "--development-fraction",
        type=_fraction,
        default=0.20,
        help="Article-family DEVELOPMENT fraction to precommit before reviewed split assignment.",
    )
    parser.add_argument(
        "--review-protocol-version",
        default="independent-double-review-v1",
    )
    parser.add_argument(
        "--benchmark-confidence",
        type=_confidence,
        default=0.95,
        help="One-sided benchmark confidence level to precommit before DEVELOPMENT/TEST evaluation.",
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

    if args.train_fraction + args.development_fraction >= 1.0:
        parser.error("train and development fractions must leave positive mass for TEST")

    sampling_frame = load_extraction_sampling_frame(args.sampling_frame)
    seed_manifest = load_extraction_seed_manifest(args.seed_manifest)
    threshold_grid = ExtractionThresholdGrid(points=tuple(args.threshold))
    plan = build_extraction_evidence_plan(
        sampling_frame,
        seed_manifest,
        threshold_grid,
        review_protocol_version=args.review_protocol_version,
        split_salt=args.split_salt,
        train_fraction=args.train_fraction,
        development_fraction=args.development_fraction,
        benchmark_confidence=args.benchmark_confidence,
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