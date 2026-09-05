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
            "--seed-manifest",
            str(root / "benchmark/extraction/seed_cases_v0.11.json"),
            "--split-salt",
            "locked-real-paper-v1",
            "--train-fraction",
            "0.55",
            "--development-fraction",
            "0.25",
            "--benchmark-confidence",
            "0.975",
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
    assert payload["plan"]["train_fraction"] == 0.55
    assert payload["plan"]["development_fraction"] == 0.25
    assert payload["plan"]["benchmark_confidence"] == 0.975
    assert [row["threshold_id"] for row in payload["threshold_grid"]] == [
        "t-080",
        "t-090",
        "t-095",
    ]
    assert "labels" not in payload
    assert "accepted_normalized_values" not in output.read_text(encoding="utf-8")


def test_extraction_evidence_plan_cli_requires_explicit_seed_manifest(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "evidence-plan.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/build_extraction_evidence_plan.py"),
            "--split-salt",
            "locked-real-paper-v1",
            "--threshold",
            "t-090=0.90",
            "--output",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "--seed-manifest" in result.stderr
    assert not output.exists()


def test_extraction_evidence_plan_cli_rejects_invalid_benchmark_confidence(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "evidence-plan.json"
    for value in ("nan", "inf", "0", "1"):
        result = subprocess.run(
            [
                sys.executable,
                str(root / "scripts/build_extraction_evidence_plan.py"),
                "--seed-manifest",
                str(root / "benchmark/extraction/seed_cases_v0.11.json"),
                "--split-salt",
                "locked-real-paper-v1",
                "--benchmark-confidence",
                value,
                "--threshold",
                "t-090=0.90",
                "--output",
                str(output),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "benchmark confidence" in result.stderr
        assert not output.exists()


def test_extraction_evidence_plan_cli_rejects_split_policy_without_test_mass(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "evidence-plan.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/build_extraction_evidence_plan.py"),
            "--seed-manifest",
            str(root / "benchmark/extraction/seed_cases_v0.11.json"),
            "--split-salt",
            "locked-real-paper-v1",
            "--train-fraction",
            "0.8",
            "--development-fraction",
            "0.2",
            "--threshold",
            "t-090=0.90",
            "--output",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "leave positive mass for TEST" in result.stderr
    assert not output.exists()