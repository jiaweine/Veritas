from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from veritas.extraction_review import ExtractionAdjudication, ExtractionReviewSubmission
from veritas.extraction_review_record_json import load_extraction_review_record
from veritas.extraction_review_submission_json import (
    extraction_adjudication_json_payload,
    extraction_review_submission_json_payload,
)
from veritas.models import SourceLocation


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _args(tmp_path: Path):
    target_id = "frontiers-1520668-table2-f01:beta"
    source = SourceLocation(
        artifact_id="doi:10.3389/fpubh.2025.1520668",
        page=7,
        table="Table 2",
        row="F01 (Group male vs. female)",
        column="Coefficient",
    )
    submissions = (
        ExtractionReviewSubmission(
            target_id=target_id,
            reviewer_id="reviewer-a",
            accepted_normalized_values=("-0.028",),
            source=source,
            note="independent review A fixture",
        ),
        ExtractionReviewSubmission(
            target_id=target_id,
            reviewer_id="reviewer-b",
            accepted_normalized_values=("-0.028",),
            source=source,
            note="independent review B fixture",
        ),
    )
    adjudication = ExtractionAdjudication(
        target_id=target_id,
        adjudicator_id="reviewer-c",
        accepted_normalized_values=("-0.028",),
        source=source,
        note="independent adjudication fixture",
    )
    submission_paths = []
    for submission in submissions:
        path = tmp_path / f"{submission.reviewer_id}.json"
        _write_json(path, extraction_review_submission_json_payload(submission))
        submission_paths.append(path)
    adjudication_path = tmp_path / "adjudication.json"
    _write_json(adjudication_path, extraction_adjudication_json_payload(adjudication))
    output = tmp_path / "review-record.json"
    args = [
        sys.executable,
        "scripts/build_extraction_review_record.py",
        "--seed-manifest",
        "benchmark/extraction/seed_cases_v0.11.json",
        "--target-id",
        target_id,
        "--kind",
        "field",
        "--adjudication",
        str(adjudication_path),
        "--output",
        str(output),
    ]
    for path in submission_paths:
        args.extend(("--submission", str(path)))
    return args, output, submissions, adjudication


def test_review_record_cli_binds_target_identity_to_strict_seed(tmp_path: Path) -> None:
    args, output, submissions, adjudication = _args(tmp_path)

    result = subprocess.run(
        args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    record = load_extraction_review_record(output)
    assert record.target.target_id == "frontiers-1520668-table2-f01:beta"
    assert record.target.paper_id == "doi:10.3389/fpubh.2025.1520668"
    assert record.target.key == "beta"
    assert record.submissions == submissions
    assert record.adjudication == adjudication
    assert result.stdout.strip() == record.sha256()


def test_review_record_cli_rejects_target_outside_seed_universe(tmp_path: Path) -> None:
    args, output, _, _ = _args(tmp_path)
    target_index = args.index("frontiers-1520668-table2-f01:beta")
    args[target_index] = "not-in-seed:beta"

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "outside the strict seed target universe" in result.stderr
    assert not output.exists()


def test_review_submission_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    args, output, _, _ = _args(tmp_path)
    submission_index = args.index("--submission") + 1
    path = Path(args[submission_index])
    text = path.read_text(encoding="utf-8")
    text = text.replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,', 1)
    path.write_text(text, encoding="utf-8")

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "duplicate JSON object key" in result.stderr
    assert not output.exists()
