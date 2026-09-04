from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_extraction_evidence_plan_cli_writes_nonproduction_pretest_commitment(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "evidence-plan.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/build_extraction_evidence_plan.py"),
            "--sampling-frame",
            str(root / "benchmark/corpus/candidates.json"),
            "--split-salt",
            "locked-real-paper-v1",
            "--threshold",
            "t-080=0.80",
            "--threshold",
            "t-090=0.90",
            "--threshold",
            "t-095=0.95",
            "--output",
            str(output),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    printed_sha = result.stdout.strip()

    assert len(printed_sha) == 64
    assert payload["plan_sha256"] == printed_sha
    assert payload["production_authorized"] is False
    assert payload["plan"]["split_salt"] == "locked-real-paper-v1"
    assert [row["threshold_id"] for row in payload["threshold_grid"]] == [
        "t-080",
        "t-090",
        "t-095",
    ]
    assert "labels" not in payload
    assert "accepted_normalized_values" not in output.read_text(encoding="utf-8")
