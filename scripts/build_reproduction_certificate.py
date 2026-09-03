from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.reproduction_ingest import build_answer_free_certificate_from_files
from veritas.reproduction_ingest_set import build_answer_free_target_set_certificate_from_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an answer-free post-run reproduction certificate from sealed private targets."
    )
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--execution", required=True, type=Path)
    private = parser.add_mutually_exclusive_group(required=True)
    private.add_argument("--private-target", type=Path)
    private.add_argument("--private-target-set", type=Path)
    parser.add_argument("--output-artifact", required=True, type=Path)
    parser.add_argument("--certificate-out", required=True, type=Path)
    args = parser.parse_args()

    if args.private_target_set is not None:
        certificate = build_answer_free_target_set_certificate_from_files(
            packet_path=args.packet,
            execution_path=args.execution,
            private_targets_path=args.private_target_set,
            output_path=args.output_artifact,
        )
    else:
        certificate = build_answer_free_certificate_from_files(
            packet_path=args.packet,
            execution_path=args.execution,
            private_target_path=args.private_target,
            output_path=args.output_artifact,
        )

    args.certificate_out.parent.mkdir(parents=True, exist_ok=True)
    args.certificate_out.write_text(
        json.dumps(certificate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(certificate, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
