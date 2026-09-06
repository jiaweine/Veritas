from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from veritas.extraction_input_artifacts import (
    build_extraction_input_artifact_manifest,
    extraction_input_artifact_manifest_payload,
)


def _artifact(value: str) -> tuple[str, str]:
    artifact_id, separator, relative_path = value.partition("=")
    if not separator or not artifact_id or not relative_path:
        raise argparse.ArgumentTypeError("artifact must use ARTIFACT_ID=relative/path syntax")
    return artifact_id, relative_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a strict input-artifact manifest from exact publication bytes."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--artifact",
        action="append",
        type=_artifact,
        required=True,
        help="Repeat ARTIFACT_ID=relative/path for every publication/input file.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = build_extraction_input_artifact_manifest(args.root, args.artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            extraction_input_artifact_manifest_payload(manifest),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(sha256(args.output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
