from __future__ import annotations

import argparse
from pathlib import Path

from veritas.harness.benchmark_runner import run_ci_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one locked Veritas benchmark/probe and emit a CI result envelope."
    )
    parser.add_argument("benchmark_id", help="Locked benchmark id from the product benchmark catalog")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".veritas-benchmark-results"),
        help="Directory for Benchmark Result Envelope v1 JSON files",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(run_ci_benchmark(args.benchmark_id, output_dir=args.output_dir))


if __name__ == "__main__":
    main()
