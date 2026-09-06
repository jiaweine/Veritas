from __future__ import annotations

import json
from pathlib import Path

from veritas.extraction_evidence_workflow import (
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_v015_real_paper_sampling_frame_and_seed_manifest_load_strictly() -> None:
    root = _root()
    frame_path = root / "benchmark/corpus/evidence_sampling_frame_v0.15.json"
    seed_path = root / "benchmark/extraction/evidence_seed_manifest_v0.15.json"

    frame = load_extraction_sampling_frame(frame_path)
    seed = load_extraction_seed_manifest(seed_path)

    assert frame.status == "sampling_frame_only_unlabeled"
    assert seed.status == "seed_corpus_not_locked_gold"
    assert seed.production_hard_finding_authorized is False

    family_by_paper = frame.paper_family_map()
    seed_paper_ids = {target.paper_id for target in seed.targets}
    assert seed_paper_ids == set(family_by_paper)
    assert all(
        family_by_paper[target.paper_id] == target.article_family_id
        for target in seed.targets
    )

    raw_frame = json.loads(frame_path.read_text(encoding="utf-8"))
    assert raw_frame["as_of"] == "2026-09-07"
    assert len(raw_frame["papers"]) == 4
    assert all(paper["artifact_urls"] for paper in raw_frame["papers"])
    assert all(paper["license_note"] for paper in raw_frame["papers"])
    assert all(paper["extraction_layout_note"] for paper in raw_frame["papers"])
    assert all(
        paper["source_metadata_verified_on"] == "2026-09-07"
        for paper in raw_frame["papers"]
    )


def test_v015_evidence_seed_does_not_relabel_legacy_parser_development_papers() -> None:
    root = _root()
    seed = load_extraction_seed_manifest(
        root / "benchmark/extraction/evidence_seed_manifest_v0.15.json"
    )
    legacy = load_extraction_seed_manifest(
        root / "benchmark/extraction/seed_cases_v0.11.json"
    )

    evidence_papers = {target.paper_id for target in seed.targets}
    legacy_papers = {target.paper_id for target in legacy.targets}
    assert evidence_papers.isdisjoint(legacy_papers)

    evidence_cases = {target.case_id for target in seed.targets}
    legacy_cases = {target.case_id for target in legacy.targets}
    assert evidence_cases.isdisjoint(legacy_cases)
