from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.benchmark import BenchmarkSplit
from veritas.extraction_evidence_plan_json import load_extraction_evidence_plan
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_evidence_workflow import (
    build_extraction_split_target_manifest,
    file_sha256,
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)
from veritas.extraction_review import build_extraction_gold_manifest
from veritas.extraction_review_record_json import load_extraction_review_record


def _validate_precommitted_inputs(plan, sampling_frame, seed_manifest) -> None:
    if sampling_frame.sha256() != plan.sampling_frame_sha256:
        raise ValueError("sampling frame does not match the precommitted evidence plan")
    if sampling_frame.source_manifest_sha256 != plan.sampling_frame_source_manifest_sha256:
        raise ValueError("sampling-frame source bytes do not match the precommitted evidence plan")
    if seed_manifest.source_manifest_sha256 != plan.source_seed_manifest_sha256:
        raise ValueError("seed-manifest source bytes do not match the precommitted evidence plan")
    if seed_manifest.sha256() != plan.seed_target_universe_sha256:
        raise ValueError("seed target universe does not match the precommitted evidence plan")


def _validate_reviewed_gold(gold_manifest, sampling_frame, seed_manifest) -> None:
    seed_targets = seed_manifest.target_map()
    family_by_paper = sampling_frame.paper_family_map()
    for target in gold_manifest.targets:
        seed_target = seed_targets.get(target.target_id)
        if seed_target is None:
            raise ValueError(
                "reviewed gold target is outside the precommitted seed target universe: "
                f"{target.target_id!r}"
            )

        seed_identity = (
            seed_target.paper_id,
            seed_target.article_family_id,
            seed_target.object_type,
            seed_target.key,
            seed_target.critical_for_hard_audit,
        )
        gold_identity = (
            target.paper_id,
            target.article_family_id,
            target.object_type,
            target.key,
            target.critical_for_hard_audit,
        )
        if seed_identity != gold_identity:
            raise ValueError(
                f"reviewed gold target identity drifted from seed manifest: {target.target_id!r}"
            )

        seed_locator = (
            seed_target.expected_page,
            seed_target.table_label,
            seed_target.row_label,
        )
        gold_locator = (
            target.source.page,
            target.source.table,
            target.source.row,
        )
        if seed_locator != gold_locator:
            raise ValueError(
                "reviewed gold source locator drifted from seed manifest: "
                f"{target.target_id!r}"
            )

        expected_family = family_by_paper.get(target.paper_id)
        if expected_family is None:
            raise ValueError(
                "reviewed gold paper is outside the precommitted sampling frame: "
                f"{target.paper_id!r}"
            )
        if expected_family != target.article_family_id:
            raise ValueError(
                f"reviewed gold article-family identity drifted: {target.target_id!r}"
            )


def _write_split_manifest(path: Path, manifest) -> str:
    path.write_text(
        json.dumps(manifest.to_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reloaded = load_extraction_split_target_manifest(path)
    if reloaded != manifest:
        raise ValueError(f"written split target manifest does not round-trip exactly: {path.name}")
    return file_sha256(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Derive canonical DEVELOPMENT and TEST target manifests mechanically from "
            "precommitted evidence inputs and independently adjudicated review records."
        )
    )
    parser.add_argument("--sampling-frame", type=Path, required=True)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--evidence-plan", type=Path, required=True)
    parser.add_argument("--review-record", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    sampling_frame = load_extraction_sampling_frame(args.sampling_frame)
    seed_manifest = load_extraction_seed_manifest(args.seed_manifest)
    plan, _ = load_extraction_evidence_plan(args.evidence_plan)
    _validate_precommitted_inputs(plan, sampling_frame, seed_manifest)

    review_records = tuple(load_extraction_review_record(path) for path in args.review_record)
    target_ids = [record.target.target_id for record in review_records]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("review-record target ids must be unique")

    gold_manifest = build_extraction_gold_manifest(
        review_records,
        split_salt=plan.split_salt,
        source_seed_manifest_sha256=plan.source_seed_manifest_sha256,
        review_protocol_version=plan.review_protocol_version,
    )
    _validate_reviewed_gold(gold_manifest, sampling_frame, seed_manifest)

    split_lock = gold_manifest.build_split_lock(
        train_fraction=plan.train_fraction,
        development_fraction=plan.development_fraction,
    )
    development_manifest = build_extraction_split_target_manifest(
        gold_manifest,
        split_lock,
        split=BenchmarkSplit.DEVELOPMENT,
    )
    test_manifest = build_extraction_split_target_manifest(
        gold_manifest,
        split_lock,
        split=BenchmarkSplit.TEST,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    development_path = args.output_dir / "development-target-manifest.json"
    test_path = args.output_dir / "test-target-manifest.json"
    development_file_sha256 = _write_split_manifest(development_path, development_manifest)
    test_file_sha256 = _write_split_manifest(test_path, test_manifest)

    index = {
        "schema_version": 1,
        "production_authorized": False,
        "evidence_plan_sha256": plan.sha256(),
        "sampling_frame_sha256": sampling_frame.sha256(),
        "sampling_frame_source_manifest_sha256": sampling_frame.source_manifest_sha256,
        "seed_target_universe_sha256": seed_manifest.sha256(),
        "source_seed_manifest_sha256": seed_manifest.source_manifest_sha256,
        "gold_manifest_sha256": gold_manifest.sha256(),
        "review_records": [
            {
                "target_id": record.target.target_id,
                "review_record_sha256": record.sha256(),
            }
            for record in sorted(review_records, key=lambda item: item.target.target_id)
        ],
        "split_lock": {
            "sha256": split_lock.sha256(),
            "split_salt": split_lock.split_salt,
            "train_fraction": float(split_lock.train_fraction),
            "development_fraction": float(split_lock.development_fraction),
            "assignments": [
                {
                    "article_family_id": family_id,
                    "split": split.value,
                }
                for family_id, split in sorted(split_lock.assignments, key=lambda item: item[0])
            ],
        },
        "development": {
            "path": development_path.name,
            "manifest_sha256": development_manifest.sha256(),
            "file_sha256": development_file_sha256,
            "article_family_ids": list(development_manifest.article_family_ids),
            "target_ids": list(development_manifest.target_ids),
        },
        "test": {
            "path": test_path.name,
            "manifest_sha256": test_manifest.sha256(),
            "file_sha256": test_file_sha256,
            "article_family_ids": list(test_manifest.article_family_ids),
            "target_ids": list(test_manifest.target_ids),
        },
    }
    index_path = args.output_dir / "split-derivation.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(index, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
