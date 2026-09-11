from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.extraction_evidence_workflow import load_extraction_seed_manifest
from veritas.extraction_review import ExtractionReviewTarget, resolve_extraction_reviews
from veritas.extraction_review_record_json import (
    extraction_review_record_json_payload,
    load_extraction_review_record,
)
from veritas.extraction_review_submission_json import (
    load_extraction_adjudication,
    load_extraction_review_submission,
)
from veritas.ingestion import EvidenceKind


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build one canonical extraction review-record archive from strict independent "
            "review submissions and a strict adjudication file, binding target identity to "
            "the exact seed manifest."
        )
    )
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument(
        "--kind",
        choices=tuple(kind.value for kind in EvidenceKind),
        required=True,
    )
    parser.add_argument("--submission", type=Path, action="append", required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    seed = load_extraction_seed_manifest(args.seed_manifest)
    seed_target = seed.target_map().get(args.target_id)
    if seed_target is None:
        raise ValueError("target_id is outside the strict seed target universe")

    target = ExtractionReviewTarget(
        target_id=seed_target.target_id,
        paper_id=seed_target.paper_id,
        article_family_id=seed_target.article_family_id,
        object_type=seed_target.object_type,
        key=seed_target.key,
        kind=EvidenceKind(args.kind),
        critical_for_hard_audit=seed_target.critical_for_hard_audit,
    )
    submissions = tuple(load_extraction_review_submission(path) for path in args.submission)
    adjudication = load_extraction_adjudication(args.adjudication)
    record = resolve_extraction_reviews(
        target,
        submissions,
        adjudication=adjudication,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            extraction_review_record_json_payload(record),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    reloaded = load_extraction_review_record(args.output)
    if reloaded != record:
        raise ValueError("written extraction review record does not round-trip exactly")
    print(record.sha256())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
