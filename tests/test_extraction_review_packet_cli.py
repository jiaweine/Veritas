from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_review_packet_cli_uses_strict_seed_loader_and_submission_schema(tmp_path: Path) -> None:
    output_dir = tmp_path / "packets"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_review_packets.py",
            "--seed",
            "benchmark/extraction/seed_cases_v0.11.json",
            "--output-dir",
            str(output_dir),
        ],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    assert summary["packet_count"] == 2
    packet = json.loads((output_dir / "reviewer-a.review-packet.json").read_text(encoding="utf-8"))
    template = packet["submission_template"]
    assert template["schema_version"] == 1
    assert "char_start" in template["source"]
    assert "char_end" in template["source"]
    assert summary["legacy_values_included"] is False
    assert summary["other_reviewer_submissions_included"] is False


def test_review_packet_cli_rejects_duplicate_seed_json_keys(tmp_path: Path) -> None:
    source = (_root() / "benchmark/extraction/seed_cases_v0.11.json").read_text(encoding="utf-8")
    source = source.replace(
        '"schema_version": 1,',
        '"schema_version": 1, "schema_version": 1,',
        1,
    )
    seed = tmp_path / "duplicate-seed.json"
    seed.write_text(source, encoding="utf-8")
    output_dir = tmp_path / "packets"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_extraction_review_packets.py",
            "--seed",
            str(seed),
            "--output-dir",
            str(output_dir),
        ],
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "duplicate JSON object key" in result.stderr
    assert not output_dir.exists()
