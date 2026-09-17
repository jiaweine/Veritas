from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..version import package_version
from .benchmark_results import BenchmarkResultStore

_MAX_RESULT_FILE_BYTES = 1024 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and persist one Veritas Benchmark Result Envelope v1."
    )
    parser.add_argument("result_file", type=Path, help="JSON result envelope to ingest")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("VERITAS_HARNESS_DATA", "~/.veritas/harness"),
        help="Harness data directory (defaults to VERITAS_HARNESS_DATA or ~/.veritas/harness)",
    )
    parser.add_argument("--version", action="version", version=package_version())
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    path = args.result_file.expanduser().resolve()
    try:
        with path.open("rb") as handle:
            source_bytes = handle.read(_MAX_RESULT_FILE_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"unable to read benchmark result: {path}") from exc
    if len(source_bytes) > _MAX_RESULT_FILE_BYTES:
        raise ValueError("benchmark result source exceeds 1 MiB")
    try:
        payload = json.loads(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("benchmark result must be UTF-8 JSON") from exc

    store = BenchmarkResultStore(Path(args.data_dir).expanduser())
    return store.ingest(payload, source_bytes=source_bytes)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        record = run(args)
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
