from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.reproduction_ingest import build_answer_free_certificate_from_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an answer-free post-run reproduction certificate from a private target."
    )
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--execution", required=True, type=Path)
    parser.add_argument("--private-target", required=True, type=Path)
    parser.add_argument("--output-artifact", required=True, type=Path)
    parser.add_argument("--certificate-out", required=True, type=Path)
    args = parser.parse_args()

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
