from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..version import package_version
from .benchmark_results import BenchmarkResultStore


def _store(data_dir: str | None) -> BenchmarkResultStore:
    root = Path(data_dir or os.environ.get("VERITAS_HARNESS_DATA", "~/.veritas/harness")).expanduser()
    return BenchmarkResultStore(root / "benchmark-results")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record or inspect durable Veritas benchmark execution provenance."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    parser.add_argument("--data-dir", help="Harness data directory (defaults to VERITAS_HARNESS_DATA).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="Record one already-completed known benchmark execution.")
    record.add_argument("--benchmark-id", required=True)
    record.add_argument("--exit-code", required=True, type=int)
    record.add_argument("--commit-sha")
    record.add_argument("--duration-ms", type=int)

    listing = subparsers.add_parser("list", help="List persisted benchmark execution records.")
    listing.add_argument("--benchmark-id")
    listing.add_argument("--limit", type=int, default=100)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = _store(args.data_dir)
    if args.command == "record":
        payload = store.record(
            benchmark_id=args.benchmark_id,
            exit_code=args.exit_code,
            commit_sha=args.commit_sha,
            duration_ms=args.duration_ms,
        )
    else:
        payload = {
            "schema_version": "1",
            "results": store.list_results(benchmark_id=args.benchmark_id, limit=args.limit),
        }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
