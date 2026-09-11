from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from veritas.benchmark import BenchmarkSplit
from veritas.corpus import assign_article_family_split
from veritas.extraction_evidence_runner import load_extraction_split_target_manifest
from veritas.extraction_evidence_workflow import (
    ExtractionThresholdGrid,
    build_extraction_evidence_plan,
    extraction_evidence_plan_payload,
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)
from veritas.extraction_review import (
    ExtractionAdjudication,
    ExtractionReviewSubmission,
    ExtractionReviewTarget,
    resolve_extraction_reviews,
)
from veritas.extraction_review_record_json import extraction_review_record_json_payload
from veritas.ingestion import EvidenceKind
from veritas.models import SourceLocation


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _choose_split_salt(family_ids: tuple[str, ...]) -> str:
    for index in range(10_000):
        salt = f"split-cli-test-{index}"
        splits = {
            assign_article_family_split(
                family_id,
                salt=salt,
                train_fraction=0.20,
                development_fraction=0.40,
            )
            for family_id in family_ids
        }
        if BenchmarkSplit.DEVELOPMENT in splits and BenchmarkSplit.TEST in splits:
            return salt
    raise AssertionError("failed to find a deterministic test salt with DEVELOPMENT and TEST families")


def _fixture(tmp_path: Path) -> tuple[list[str], Path, Path, list[Path]]:
    families = ("family-a", "family-b", "family-c")
    papers = [
        {
            "paper_id": f"paper-{index}",
            "article_family_id": family_id,
            "doi": None,
            "title": f"Paper {index}",
            "discipline": "test",
            "year": 2026,
            "source_url": f"https://example.test/paper-{index}",
            "access_tier": "paper_only",
            "artifact_urls": [],
            "license_note": None,
            "redistributable_artifacts": False,
        }
        for index, family_id in enumerate(families, start=1)
    ]
    sampling_path = tmp_path / "sampling.json"
    _write_json(
        sampling_path,
        {
            "schema_version": 1,
            "status": "sampling_frame_only_unlabeled",
            "papers": papers,
        },
    )

    cases = [
        {
            "case_id": f"case-{index}",
            "paper_id": f"paper-{index}",
            "article_family_id": family_id,
            "doi": None,
            "pdf_url": f"https://example.test/paper-{index}.pdf",
            "object_type": "RegressionResult",
            "split": None,
            "locator": {
                "expected_page": index,
                "table_label": f"Table {index}",
                "row_label": f"row-{index}",
            },
            "expected_fields": {"beta": None},
        }
        for index, family_id in enumerate(families, start=1)
    ]
    seed_path = tmp_path / "seed.json"
    _write_json(
        seed_path,
        {
            "schema_version": 1,
            "status": "seed_corpus_not_locked_gold",
            "production_hard_finding_authorized": False,
            "cases": cases,
        },
    )

    sampling_frame = load_extraction_sampling_frame(sampling_path)
    seed_manifest = load_extraction_seed_manifest(seed_path)
    split_salt = _choose_split_salt(families)
    threshold_grid = ExtractionThresholdGrid(points=(("nc-010", 0.01),))
    plan = build_extraction_evidence_plan(
        sampling_frame,
        seed_manifest,
        threshold_grid,
        split_salt=split_salt,
        train_fraction=0.20,
        development_fraction=0.40,
    )
    evidence_plan_path = tmp_path / "evidence-plan.json"
    _write_json(evidence_plan_path, extraction_evidence_plan_payload(plan, threshold_grid))

    record_paths: list[Path] = []
    for seed_target in seed_manifest.targets:
        target = ExtractionReviewTarget(
            target_id=seed_target.target_id,
            paper_id=seed_target.paper_id,
            article_family_id=seed_target.article_family_id,
            object_type=seed_target.object_type,
            key=seed_target.key,
            kind=EvidenceKind.FIELD,
            critical_for_hard_audit=seed_target.critical_for_hard_audit,
        )
        source = SourceLocation(
            artifact_id=f"artifact-{seed_target.paper_id}",
            page=seed_target.expected_page,
            table=seed_target.table_label,
            row=seed_target.row_label,
            column="Coefficient",
        )
        submissions = (
            ExtractionReviewSubmission(
                target_id=seed_target.target_id,
                reviewer_id=f"reviewer-a-{seed_target.paper_id}",
                accepted_normalized_values=("0.100",),
                source=source,
                note="independent reviewer A fixture",
            ),
            ExtractionReviewSubmission(
                target_id=seed_target.target_id,
                reviewer_id=f"reviewer-b-{seed_target.paper_id}",
                accepted_normalized_values=("0.100",),
                source=source,
                note="independent reviewer B fixture",
            ),
        )
        adjudication = ExtractionAdjudication(
            target_id=seed_target.target_id,
            adjudicator_id=f"adjudicator-{seed_target.paper_id}",
            accepted_normalized_values=("0.100",),
            source=source,
            note="independent adjudication fixture",
        )
        record = resolve_extraction_reviews(target, submissions, adjudication=adjudication)
        record_path = tmp_path / f"{seed_target.target_id.replace(':', '-')}.review-record.json"
        _write_json(record_path, extraction_review_record_json_payload(record))
        record_paths.append(record_path)

    output_dir = tmp_path / "split-output"
    args = [
        sys.executable,
        "scripts/build_extraction_split_manifests.py",
        "--sampling-frame",
        str(sampling_path),
        "--seed-manifest",
        str(seed_path),
        "--evidence-plan",
        str(evidence_plan_path),
        "--output-dir",
        str(output_dir),
    ]
    for path in record_paths:
        args.extend(("--review-record", str(path)))
    return args, output_dir, seed_path, record_paths


def test_split_manifest_cli_derives_canonical_development_and_test_manifests(
    tmp_path: Path,
) -> None:
    args, output_dir, _, _ = _fixture(tmp_path)

    result = subprocess.run(
        args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    index = json.loads(result.stdout)
    development_path = output_dir / "development-target-manifest.json"
    test_path = output_dir / "test-target-manifest.json"
    development = load_extraction_split_target_manifest(development_path)
    test = load_extraction_split_target_manifest(test_path)

    assert development.split is BenchmarkSplit.DEVELOPMENT
    assert test.split is BenchmarkSplit.TEST
    assert set(development.article_family_ids).isdisjoint(test.article_family_ids)
    assert set(development.target_ids).isdisjoint(test.target_ids)
    assert index["gold_manifest_sha256"] == development.gold_manifest_sha256
    assert index["gold_manifest_sha256"] == test.gold_manifest_sha256
    assert index["split_lock"]["sha256"] == development.split_lock_sha256
    assert index["split_lock"]["sha256"] == test.split_lock_sha256
    assert index["development"]["manifest_sha256"] == development.sha256()
    assert index["test"]["manifest_sha256"] == test.sha256()
    assert index["development"]["file_sha256"] == hashlib.sha256(
        development_path.read_bytes()
    ).hexdigest()
    assert index["test"]["file_sha256"] == hashlib.sha256(test_path.read_bytes()).hexdigest()
    assert index["production_authorized"] is False
    assert (output_dir / "split-derivation.json").is_file()


def test_split_manifest_cli_rejects_seed_byte_drift_after_precommit(tmp_path: Path) -> None:
    args, output_dir, seed_path, _ = _fixture(tmp_path)
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    seed_path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "seed-manifest source bytes do not match the precommitted evidence plan" in result.stderr
    assert not output_dir.exists()


def test_split_manifest_cli_rejects_review_source_locator_drift(tmp_path: Path) -> None:
    args, output_dir, _, record_paths = _fixture(tmp_path)
    path = record_paths[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source"]["row"] = "wrong-row"
    payload["adjudication"]["source"]["row"] = "wrong-row"
    _write_json(path, payload)

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "reviewed gold source locator drifted from seed manifest" in result.stderr
    assert not output_dir.exists()
