from __future__ import annotations

import json
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST = _REPO_ROOT / "benchmark" / "reproduction" / "candidates_v0.11.json"
_FORBIDDEN_KEYS = {
    "reported",
    "reported_value",
    "reported_values",
    "expected",
    "expected_value",
    "expected_values",
    "target_value",
    "target_values",
    "paper_result",
    "paper_results",
}


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_reproduction_candidate_manifest_is_explicitly_non_gold_and_answer_free() -> None:
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))

    assert payload["status"] == "sampling_frame_only_no_reported_targets"
    assert _FORBIDDEN_KEYS.isdisjoint(_keys(payload))
    assert payload["candidates"]
    assert all("blind_agent_benchmark_status" in item for item in payload["candidates"])
    assert not any(
        item["blind_agent_benchmark_status"] == "benchmark_gold"
        for item in payload["candidates"]
    )
