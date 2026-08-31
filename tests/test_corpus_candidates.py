from __future__ import annotations

import json
from pathlib import Path

from veritas.corpus import AccessTier, CorpusPaper


def test_real_corpus_candidates_are_schema_valid_and_unlabeled():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "benchmark/corpus/candidates.json").read_text(encoding="utf-8"))
    assert payload["status"] == "sampling_frame_only_unlabeled"
    assert "labels" not in payload
    assert payload["papers"]

    papers = []
    for raw in payload["papers"]:
        paper = CorpusPaper(
            paper_id=raw["paper_id"],
            article_family_id=raw["article_family_id"],
            doi=raw.get("doi"),
            title=raw["title"],
            discipline=raw["discipline"],
            year=raw["year"],
            source_url=raw["source_url"],
            access_tier=AccessTier(raw["access_tier"]),
            artifact_urls=tuple(raw.get("artifact_urls", ())),
            license_note=raw.get("license_note"),
            redistributable_artifacts=raw.get("redistributable_artifacts", False),
        )
        assert paper.redistributable_artifacts is False
        papers.append(paper)

    assert len({paper.paper_id for paper in papers}) == len(papers)
    assert len({paper.article_family_id for paper in papers}) == len(papers)
