from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.extraction_execution_artifacts import (
    build_extraction_execution_plan_from_artifacts,
)
from veritas.extraction_execution_evidence_json import extraction_execution_plan_json_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a safe pre-TEST ExtractionExecutionPlan from exact archived artifact bytes."
        )
    )
    parser.add_argument("--input-artifact-manifest", type=Path, required=True)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--parser-registry", type=Path, required=True)
    parser.add_argument("--numerical-runtime", type=Path, required=True)
    parser.add_argument("--execution-command", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = build_extraction_execution_plan_from_artifacts(
        input_artifact_manifest=args.input_artifact_manifest,
        source_tree=args.source_tree,
        parser_registry=args.parser_registry,
        numerical_runtime=args.numerical_runtime,
        execution_command=args.execution_command,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            extraction_execution_plan_json_payload(plan),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(plan.sha256())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
