from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_bound_extraction_external_provenance_cli import _bound_fixture, _file_sha256
from test_extraction_external_provenance_cli import _root

from veritas.extraction_input_artifacts import load_extraction_input_artifact_manifest
from veritas.extraction_release_archive import load_extraction_release_evidence_bundle


def _arg(args: list[str], name: str) -> str:
    return args[args.index(name) + 1]


def _run_bound_then_handoff(tmp_path: Path):
    fixture = _bound_fixture(tmp_path)
    subprocess.run(
        fixture["args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    handoff_path = tmp_path / "postverification-external-handoff.json"
    args = list(fixture["args"])
    args[1] = "scripts/build_extraction_postverification_external_handoff.py"
    args[args.index("--output") + 1] = str(handoff_path)
    args.extend(("--bound-verification", str(fixture["output_path"])))
    return fixture, args, handoff_path


def test_postverification_handoff_archives_complete_bound_replay_set(tmp_path: Path) -> None:
    fixture, args, handoff_path = _run_bound_then_handoff(tmp_path)
    result = subprocess.run(
        args,
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert payload["status"] == (
        "repository_side_postverification_external_archive_handoff_ready_"
        "awaiting_independent_archive"
    )
    assert payload["production_authorized"] is False
    assert payload["pending_external_evidence"] == {
        "independent_archive_receipt_present": False,
        "independent_control_established": False,
        "historical_channel_semantics_established": False,
    }
    assert payload["external_provenance"][
        "original_signed_statement_directly_commits_release_sidecars"
    ] is False
    assert payload["bound_verification"]["file_sha256"] == _file_sha256(
        fixture["output_path"]
    )
    assert payload["bound_verification"][
        "release_calibration_binding_sha256"
    ] == fixture["calibration_binding"].sha256()
    assert payload["bound_verification"][
        "release_execution_binding_sha256"
    ] == fixture["execution_binding"].sha256()

    archive_names = {row["archive_name"] for row in payload["archive_objects"]}
    required_names = {
        "verification/bound-cold-verification.json",
        "release/release-evidence-bundle.json",
        "release/release-calibration-binding.json",
        "release/release-execution-binding.json",
        "release/attested-release.json",
        "provenance/signed-external-provenance.json",
        "execution/source-tree.tar",
    }
    assert required_names <= archive_names

    bundle = load_extraction_release_evidence_bundle(fixture["bundle_path"])
    expected_prediction_names = {
        f"predictions/development/{run.threshold_id}.json"
        for run in bundle.development_runs
    } | {
        f"predictions/test/{run.threshold_id}.json" for run in bundle.test_runs
    }
    assert expected_prediction_names <= archive_names

    input_manifest = load_extraction_input_artifact_manifest(
        Path(_arg(args, "--input-artifact-manifest"))
    )
    expected_publication_names = {
        f"publication-inputs/{artifact.relative_path}"
        for artifact in input_manifest.artifacts
    }
    assert expected_publication_names <= archive_names

    stable_rows = [
        {
            "archive_name": row["archive_name"],
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
        }
        for row in payload["archive_objects"]
    ]
    import hashlib

    expected_set_sha = hashlib.sha256(
        json.dumps(
            stable_rows,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert payload["archive_object_set_sha256"] == expected_set_sha
    assert result.stdout.strip() == _file_sha256(handoff_path)


def test_postverification_handoff_rejects_reformatted_bound_verification(tmp_path: Path) -> None:
    _, args, handoff_path = _run_bound_then_handoff(tmp_path)
    bound_path = Path(_arg(args, "--bound-verification"))
    payload = json.loads(bound_path.read_text(encoding="utf-8"))
    bound_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "bytes are not canonical JSON" in result.stderr
    assert not handoff_path.exists()


def test_postverification_handoff_rejects_release_sidecar_exact_byte_drift(
    tmp_path: Path,
) -> None:
    _, args, handoff_path = _run_bound_then_handoff(tmp_path)
    binding_path = Path(_arg(args, "--release-execution-binding"))
    payload = json.loads(binding_path.read_text(encoding="utf-8"))
    binding_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "release_execution_binding_file_sha256" in result.stderr or "binding" in result.stderr
    assert not handoff_path.exists()


def test_postverification_handoff_rejects_missing_prediction_replay_bytes(tmp_path: Path) -> None:
    fixture, args, handoff_path = _run_bound_then_handoff(tmp_path)
    bundle = load_extraction_release_evidence_bundle(fixture["bundle_path"])
    victim = fixture["release_artifact_root"] / bundle.test_runs[0].prediction_artifact_path
    victim.unlink()

    result = subprocess.run(
        args,
        cwd=_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "prediction" in result.stderr.lower() or "no such file" in result.stderr.lower()
    assert not handoff_path.exists()
