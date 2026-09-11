from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_extraction_external_provenance import _COMMIT_SHA, _keypair, _trust_root

from veritas.benchmark import BenchmarkSplit
from veritas.extraction import ExtractionCandidate, ExtractionDecision, ExtractionResolution
from veritas.extraction_benchmark import ExtractionPrediction
from veritas.extraction_calibration import ExtractionThresholdPolicy
from veritas.extraction_evidence_plan_json import extraction_evidence_plan_json_payload
from veritas.extraction_evidence_workflow import (
    ExtractionThresholdGrid,
    build_extraction_evidence_plan,
    build_extraction_split_target_manifest,
    load_extraction_sampling_frame,
    load_extraction_seed_manifest,
)
from veritas.extraction_execution_artifacts import build_extraction_execution_plan_from_artifacts
from veritas.extraction_execution_evidence import (
    extraction_prediction_artifact_bytes,
)
from veritas.extraction_execution_evidence_json import (
    attested_extraction_evidence_release_receipt_json_payload,
    extraction_execution_plan_json_payload,
)
from veritas.extraction_external_provenance import (
    ExtractionSignedExternalProvenance,
    build_extraction_external_provenance_statement,
    extraction_external_provenance_statement_bytes,
)
from veritas.extraction_external_provenance_json import (
    extraction_external_trust_root_payload,
    extraction_signed_external_provenance_payload,
)
from veritas.extraction_external_trust_policy import build_extraction_external_trust_policy
from veritas.extraction_external_trust_policy_json import (
    extraction_external_trust_policy_json_payload,
)
from veritas.extraction_input_artifacts import (
    build_extraction_input_artifact_manifest,
    extraction_input_artifact_manifest_payload,
)
from veritas.extraction_release_archive import (
    ExtractionArchivedThresholdRun,
    ExtractionReleaseEvidenceBundle,
    extraction_release_evidence_bundle_payload,
    rebuild_attested_extraction_evidence_release_receipt_from_archive,
)
from veritas.extraction_review import (
    ExtractionAdjudication,
    ExtractionReviewSubmission,
    ExtractionReviewTarget,
    build_extraction_gold_manifest,
    resolve_extraction_reviews,
)
from veritas.ingestion import EvidenceKind
from veritas.models import SourceLocation


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_manifests(tmp_path: Path):
    sampling_path = tmp_path / "sampling-frame.json"
    seed_path = tmp_path / "seed-manifest.json"
    papers = []
    cases = []
    for index in range(24):
        paper_id = f"paper-{index:02d}"
        family_id = f"family-{index:02d}"
        value = f"{index / 100:.2f}"
        papers.append(
            {
                "paper_id": paper_id,
                "article_family_id": family_id,
                "doi": None,
                "title": f"Paper {index}",
                "discipline": "cold_archive_fixture",
                "year": 2025,
                "source_url": f"https://example.org/{paper_id}",
                "access_tier": "paper_only",
                "artifact_urls": [f"https://example.org/{paper_id}.pdf"],
                "license_note": "synthetic test fixture",
                "redistributable_artifacts": False,
            }
        )
        cases.append(
            {
                "case_id": f"case-{index:02d}",
                "paper_id": paper_id,
                "article_family_id": family_id,
                "doi": None,
                "pdf_url": f"https://example.org/{paper_id}.pdf",
                "license_note": "synthetic test fixture",
                "object_type": "RegressionResult",
                "locator": {
                    "expected_page": 2,
                    "table_label": "Table 1",
                    "row_label": f"row-{index}",
                },
                "expected_fields": {"beta": value},
                "promotion_expectation": {
                    "detector_ready_under_geometry_probe": True,
                    "reason": "synthetic test fixture",
                },
                "review_status": "synthetic independent-review fixture",
                "split": None,
            }
        )
    _write_json(
        sampling_path,
        {
            "schema_version": 1,
            "status": "sampling_frame_only_unlabeled",
            "papers": papers,
        },
    )
    _write_json(
        seed_path,
        {
            "schema_version": 1,
            "status": "seed_corpus_not_locked_gold",
            "production_hard_finding_authorized": False,
            "cases": cases,
        },
    )
    return sampling_path, seed_path


def _review_records(seed_manifest):
    records = []
    for index, seed_target in enumerate(seed_manifest.targets):
        value = f"{index / 100:.2f}"
        source = SourceLocation(
            artifact_id=seed_target.paper_id,
            page=seed_target.expected_page,
            table=seed_target.table_label,
            row=seed_target.row_label,
            column=seed_target.key,
        )
        target = ExtractionReviewTarget(
            target_id=seed_target.target_id,
            paper_id=seed_target.paper_id,
            article_family_id=seed_target.article_family_id,
            object_type=seed_target.object_type,
            key=seed_target.key,
            kind=EvidenceKind.FIELD,
            critical_for_hard_audit=seed_target.critical_for_hard_audit,
        )
        submissions = tuple(
            ExtractionReviewSubmission(
                target_id=seed_target.target_id,
                reviewer_id=reviewer_id,
                accepted_normalized_values=(value,),
                source=source,
                note="independent synthetic cold-archive review",
            )
            for reviewer_id in ("reviewer-a", "reviewer-b")
        )
        adjudication = ExtractionAdjudication(
            target_id=seed_target.target_id,
            adjudicator_id="reviewer-c",
            accepted_normalized_values=(value,),
            source=source,
            note="independent synthetic cold-archive adjudication",
        )
        records.append(resolve_extraction_reviews(target, submissions, adjudication=adjudication))
    return tuple(records)


def _gold_subset(gold, target_ids):
    ids = set(target_ids)
    return tuple(target for target in gold.targets if target.target_id in ids)


def _prediction_set(gold, accepted_count: int, *, threshold: float):
    predictions = []
    for index, target in enumerate(gold):
        if index >= accepted_count:
            continue
        value = target.accepted_normalized_values[0]
        candidates = tuple(
            ExtractionCandidate(
                parser_id=parser_id,
                parser_family=parser_family,
                raw=value,
                normalized_value=value,
                nonconformity_score=0.0,
                source=target.source,
            )
            for parser_id, parser_family in (
                ("native", "native_pdf"),
                ("vision", "vision_language"),
            )
        )
        predictions.append(
            ExtractionPrediction(
                target_id=target.target_id,
                resolution=ExtractionResolution(
                    decision=ExtractionDecision.ACCEPT,
                    normalized_value=value,
                    accepted_candidates=candidates,
                    calibration_threshold=threshold,
                    reason="synthetic cold-archive fixture",
                ),
            )
        )
    return tuple(predictions)


def _release_bundle(tmp_path: Path, plan, grid, seed_manifest, review_records):
    gold = build_extraction_gold_manifest(
        review_records,
        split_salt=plan.split_salt,
        source_seed_manifest_sha256=seed_manifest.source_manifest_sha256,
        review_protocol_version=plan.review_protocol_version,
    )
    split_lock = gold.build_split_lock(
        train_fraction=plan.train_fraction,
        development_fraction=plan.development_fraction,
    )
    development_manifest = build_extraction_split_target_manifest(
        gold,
        split_lock,
        split=BenchmarkSplit.DEVELOPMENT,
    )
    test_manifest = build_extraction_split_target_manifest(
        gold,
        split_lock,
        split=BenchmarkSplit.TEST,
    )
    development_gold = _gold_subset(gold, development_manifest.target_ids)
    test_gold = _gold_subset(gold, test_manifest.target_ids)
    artifact_root = tmp_path / "release-artifacts"
    artifact_root.mkdir()

    def write_runs(gold_targets, split: str):
        runs = []
        split_root = artifact_root / split
        split_root.mkdir()
        accepted_counts = (
            len(gold_targets),
            max(len(gold_targets) - 1, 0),
            max(len(gold_targets) - 2, 0),
        )
        for (threshold_id, threshold), accepted_count in zip(
            grid.points,
            accepted_counts,
            strict=True,
        ):
            predictions = _prediction_set(
                gold_targets,
                accepted_count,
                threshold=float(threshold),
            )
            relative_path = f"{split}/{threshold_id}.predictions.json"
            (artifact_root / relative_path).write_bytes(
                extraction_prediction_artifact_bytes(predictions)
            )
            runs.append(
                ExtractionArchivedThresholdRun(
                    threshold_id=threshold_id,
                    threshold=float(threshold),
                    execution_id=f"{split}-{threshold_id}",
                    prediction_artifact_path=relative_path,
                )
            )
        return tuple(runs)

    bundle = ExtractionReleaseEvidenceBundle(
        review_records=review_records,
        threshold_policy=ExtractionThresholdPolicy(
            min_selective_coverage=0.0,
            min_accepted_full_accuracy=0.0,
            max_critical_family_wrong_accept_upper_bound=1.0,
        ),
        development_runs=write_runs(development_gold, "development"),
        test_runs=write_runs(test_gold, "test"),
    )
    bundle_path = tmp_path / "release-bundle.json"
    _write_json(bundle_path, extraction_release_evidence_bundle_payload(bundle))
    return bundle, bundle_path, artifact_root


def _execution_artifacts(tmp_path: Path, paper_ids: tuple[str, ...]):
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    artifact_entries = []
    publication_paths = []
    for paper_id in paper_ids:
        relative_path = f"{paper_id}.pdf"
        path = input_root / relative_path
        path.write_bytes(f"publication-bytes:{paper_id}".encode())
        artifact_entries.append((paper_id, relative_path))
        publication_paths.append(path)
    manifest = build_extraction_input_artifact_manifest(input_root, tuple(artifact_entries))
    manifest_path = tmp_path / "input-artifact-manifest.json"
    _write_json(manifest_path, extraction_input_artifact_manifest_payload(manifest))
    payloads = {
        "source_tree": b"source-tree-archive\n",
        "parser_registry": b'{"parser":"table-v1"}\n',
        "numerical_runtime": b'{"python":"3.12"}\n',
        "execution_command": b"python -m veritas.extract --frozen\n",
    }
    files: dict[str, Path] = {
        "input_artifact_manifest": manifest_path,
        "input_artifact_root": input_root,
    }
    for name, payload in payloads.items():
        path = tmp_path / f"{name}.artifact"
        path.write_bytes(payload)
        files[name] = path
    return files, tuple(publication_paths)


def _artifact_cli_args(artifacts: dict[str, Path]) -> list[str]:
    return [
        "--input-artifact-manifest",
        str(artifacts["input_artifact_manifest"]),
        "--input-artifact-root",
        str(artifacts["input_artifact_root"]),
        "--source-tree",
        str(artifacts["source_tree"]),
        "--parser-registry",
        str(artifacts["parser_registry"]),
        "--numerical-runtime",
        str(artifacts["numerical_runtime"]),
        "--execution-command",
        str(artifacts["execution_command"]),
    ]


def _archived_fixture(tmp_path: Path):
    sampling_path, seed_path = _source_manifests(tmp_path)
    sampling_frame = load_extraction_sampling_frame(sampling_path)
    seed_manifest = load_extraction_seed_manifest(seed_path)
    grid = ExtractionThresholdGrid(
        (("t-080", 0.80), ("t-090", 0.90), ("t-095", 0.95))
    )
    plan = build_extraction_evidence_plan(
        sampling_frame,
        seed_manifest,
        grid,
        split_salt="release-workflow-v1",
        benchmark_confidence=0.95,
    )
    review_records = _review_records(seed_manifest)
    bundle, bundle_path, release_artifact_root = _release_bundle(
        tmp_path,
        plan,
        grid,
        seed_manifest,
        review_records,
    )
    paper_ids = tuple(paper.paper_id for paper in sampling_frame.papers)
    artifacts, publication_paths = _execution_artifacts(tmp_path, paper_ids)
    execution_plan = build_extraction_execution_plan_from_artifacts(**artifacts)
    attested_release = rebuild_attested_extraction_evidence_release_receipt_from_archive(
        bundle,
        release_artifact_root=release_artifact_root,
        plan=plan,
        sampling_frame=sampling_frame,
        seed_manifest=seed_manifest,
        threshold_grid=grid,
        execution_plan=execution_plan,
    )

    private_key, public_key_hex = _keypair()
    trust_root = _trust_root(public_key_hex)
    statement = build_extraction_external_provenance_statement(
        trust_root=trust_root,
        run_id="33906297424",
        run_attempt=1,
        commit_sha=_COMMIT_SHA,
        attested_release_receipt=attested_release,
        execution_plan=execution_plan,
    )
    signed = ExtractionSignedExternalProvenance(
        statement=statement,
        signature_hex=private_key.sign(
            extraction_external_provenance_statement_bytes(statement)
        ).hex(),
    )
    policy = build_extraction_external_trust_policy(
        policy_id="real-extraction-run-v1",
        evidence_plan_sha256=plan.sha256(),
        execution_plan=execution_plan,
        source_commit_sha=statement.commit_sha,
        trust_root=trust_root,
    )

    evidence_plan_path = tmp_path / "evidence-plan.json"
    trust_root_path = tmp_path / "trust-root.json"
    trust_policy_path = tmp_path / "trust-policy.json"
    signed_path = tmp_path / "signed-provenance.json"
    execution_plan_path = tmp_path / "execution-plan.json"
    attested_release_path = tmp_path / "attested-release.json"
    output_path = tmp_path / "verified-receipt.json"
    _write_json(evidence_plan_path, extraction_evidence_plan_json_payload(plan, grid))
    _write_json(trust_root_path, extraction_external_trust_root_payload(trust_root))
    _write_json(trust_policy_path, extraction_external_trust_policy_json_payload(policy))
    _write_json(signed_path, extraction_signed_external_provenance_payload(signed))
    _write_json(execution_plan_path, extraction_execution_plan_json_payload(execution_plan))
    _write_json(
        attested_release_path,
        attested_extraction_evidence_release_receipt_json_payload(attested_release),
    )

    args = [
        sys.executable,
        "scripts/verify_extraction_external_provenance.py",
        "--sampling-frame",
        str(sampling_path),
        "--seed-manifest",
        str(seed_path),
        "--evidence-plan",
        str(evidence_plan_path),
        "--release-bundle",
        str(bundle_path),
        "--release-artifact-root",
        str(release_artifact_root),
        "--trust-root",
        str(trust_root_path),
        "--trust-policy",
        str(trust_policy_path),
        "--signed-provenance",
        str(signed_path),
        "--execution-plan",
        str(execution_plan_path),
        *_artifact_cli_args(artifacts),
        "--attested-release",
        str(attested_release_path),
        "--expected-run-id",
        signed.statement.run_id,
        "--expected-run-attempt",
        str(signed.statement.run_attempt),
        "--expected-commit-sha",
        signed.statement.commit_sha,
        "--output",
        str(output_path),
    ]
    return {
        "args": args,
        "output_path": output_path,
        "evidence_plan_sha256": plan.sha256(),
        "commit_sha": signed.statement.commit_sha,
        "artifacts": artifacts,
        "publication_paths": publication_paths,
        "bundle_path": bundle_path,
        "release_artifact_root": release_artifact_root,
        "first_prediction_path": (
            release_artifact_root / bundle.development_runs[0].prediction_artifact_path
        ),
    }


def test_archived_provenance_cli_cold_rebuilds_exact_precommitted_run(tmp_path: Path) -> None:
    fixture = _archived_fixture(tmp_path)
    result = subprocess.run(
        fixture["args"],
        cwd=_root(),
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(fixture["output_path"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["receipt"]["evidence_plan_sha256"] == fixture["evidence_plan_sha256"]
    assert payload["receipt"]["source_commit_sha"] == fixture["commit_sha"]
    assert payload["receipt"]["production_authorized"] is False
    assert len(payload["release_bundle_sha256"]) == 64
    assert len(payload["rebuilt_attested_release_sha256"]) == 64
    assert result.stdout.strip() == payload["receipt_sha256"]


def test_archived_provenance_cli_rejects_wrong_expected_commit(tmp_path: Path) -> None:
    fixture = _archived_fixture(tmp_path)
    commit_index = fixture["args"].index(fixture["commit_sha"])
    fixture["args"][commit_index] = "f" * 40

    result = subprocess.run(
        fixture["args"], cwd=_root(), check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "external trust policy is bound to a different source commit" in result.stderr


def test_archived_provenance_cli_rejects_execution_artifact_byte_drift(
    tmp_path: Path,
) -> None:
    fixture = _archived_fixture(tmp_path)
    fixture["artifacts"]["numerical_runtime"].write_bytes(b'{"python":"post-hoc"}\n')

    result = subprocess.run(
        fixture["args"], cwd=_root(), check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "numerical runtime differs from archived artifact bytes" in result.stderr


def test_archived_provenance_cli_rejects_publication_byte_drift(tmp_path: Path) -> None:
    fixture = _archived_fixture(tmp_path)
    fixture["publication_paths"][0].write_bytes(b"post-hoc-publication")

    result = subprocess.run(
        fixture["args"], cwd=_root(), check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "input artifact" in result.stderr


def test_archived_provenance_cli_rejects_prediction_artifact_byte_drift(
    tmp_path: Path,
) -> None:
    fixture = _archived_fixture(tmp_path)
    path = fixture["first_prediction_path"]
    path.write_bytes(path.read_bytes() + b"\n")

    result = subprocess.run(
        fixture["args"], cwd=_root(), check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "canonical JSON contract" in result.stderr


def test_archived_provenance_cli_rejects_review_record_drift(tmp_path: Path) -> None:
    fixture = _archived_fixture(tmp_path)
    payload = json.loads(fixture["bundle_path"].read_text(encoding="utf-8"))
    payload["review_records"][0]["adjudication"]["adjudicator_id"] = "reviewer-d"
    _write_json(fixture["bundle_path"], payload)

    result = subprocess.run(
        fixture["args"], cwd=_root(), check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "archived attested release differs from release rebuilt" in result.stderr


def test_archived_provenance_cli_rejects_unverified_release_source(tmp_path: Path) -> None:
    fixture = _archived_fixture(tmp_path)
    payload = json.loads(fixture["bundle_path"].read_text(encoding="utf-8"))
    record = payload["review_records"][0]
    record["source"]["artifact_id"] = "unverified-paper"
    record["adjudication"]["source"]["artifact_id"] = "unverified-paper"
    _write_json(fixture["bundle_path"], payload)

    result = subprocess.run(
        fixture["args"], cwd=_root(), check=False, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "outside the verified input-artifact manifest" in result.stderr
