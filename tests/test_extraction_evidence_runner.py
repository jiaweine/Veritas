from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from veritas.benchmark import BenchmarkSplit
from veritas.extraction import ExtractionCandidate, ExtractionDecision
from veritas.extraction_evidence_runner import (
    load_blinded_extraction_reviewer_packet,
    resolve_extraction_candidates_at_threshold,
    run_extraction_evidence_threshold,
)
from veritas.extraction_evidence_workflow import ExtractionSplitTargetManifest
from veritas.extraction_input_artifacts import (
    build_extraction_input_artifact_manifest,
    extraction_input_artifact_manifest_payload,
)
from veritas.extraction_review_packet import ExtractionReviewPacketTarget, ExtractionReviewerPacket
from veritas.models import SourceLocation


def _candidate(*, family: str, value: str = "1.23", score: float = 0.01) -> ExtractionCandidate:
    return ExtractionCandidate(
        parser_id=f"{family}:native",
        parser_family=family,
        raw=value,
        normalized_value=value,
        nonconformity_score=score,
        source=SourceLocation(
            artifact_id="paper-artifact",
            page=1,
            table="Table 1 [native-table:1]",
            row="Example row",
            text_quote=value,
        ),
    )


def _packet(*, key: str = "beta") -> ExtractionReviewerPacket:
    return ExtractionReviewerPacket(
        reviewer_slot="reviewer-a",
        seed_manifest_sha256="a" * 64,
        targets=(
            ExtractionReviewPacketTarget(
                target_id=f"case-1:{key}",
                case_id="case-1",
                paper_id="doi:10.0000/example",
                article_family_id="doi:10.0000/example",
                doi="10.0000/example",
                pdf_url="https://example.test/paper.pdf",
                object_type="RegressionResult",
                key=key,
                expected_page=1,
                table_label="Table 1",
                row_label="Example row",
            ),
        ),
    )


def _write_json(path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_blinded_packet_loader_rejects_value_bearing_target_fields(tmp_path) -> None:
    packet = _packet()
    payload = packet.to_payload()
    payload["targets"][0]["expected_fields"] = {"beta": "1.23"}
    path = tmp_path / "packet.json"
    _write_json(path, payload)

    with pytest.raises(ValueError, match="keys differ from schema"):
        load_blinded_extraction_reviewer_packet(path)


def test_frozen_threshold_resolution_requires_two_families_and_agreement() -> None:
    left = _candidate(family="family-a")
    right = _candidate(family="family-b")
    accepted = resolve_extraction_candidates_at_threshold((left, right), threshold=0.01)
    assert accepted.decision is ExtractionDecision.ACCEPT
    assert accepted.normalized_value == "1.23"

    one_family = resolve_extraction_candidates_at_threshold((left,), threshold=0.01)
    assert one_family.decision is ExtractionDecision.ABSTAIN

    conflict = resolve_extraction_candidates_at_threshold(
        (left, _candidate(family="family-b", value="1.24")),
        threshold=0.01,
    )
    assert conflict.decision is ExtractionDecision.CONFLICT

    above_threshold = resolve_extraction_candidates_at_threshold((left, right), threshold=0.005)
    assert above_threshold.decision is ExtractionDecision.ABSTAIN


def test_runner_uses_verified_local_bytes_and_blinded_targets(monkeypatch, tmp_path) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    publication = input_root / "paper.pdf"
    publication.write_bytes(b"%PDF-1.7\nsynthetic test fixture only\n")
    manifest = build_extraction_input_artifact_manifest(
        input_root,
        (("paper-artifact", "paper.pdf"),),
    )
    manifest_path = tmp_path / "input-manifest.json"
    _write_json(manifest_path, extraction_input_artifact_manifest_payload(manifest))

    packet = _packet()
    packet_path = tmp_path / "reviewer-a.review-packet.json"
    _write_json(packet_path, packet.to_payload())

    target_manifest = ExtractionSplitTargetManifest(
        split=BenchmarkSplit.DEVELOPMENT,
        gold_manifest_sha256="b" * 64,
        split_lock_sha256="c" * 64,
        article_family_ids=("doi:10.0000/example",),
        target_ids=("case-1:beta",),
    )
    target_manifest_path = tmp_path / "development-targets.json"
    _write_json(target_manifest_path, target_manifest.to_payload())

    parse_calls: list[tuple[bytes, str]] = []

    def fake_parse(pdf_bytes: bytes, *, artifact_id: str):
        parse_calls.append((pdf_bytes, artifact_id))
        return (object(), object())

    bundle = SimpleNamespace(
        ambiguities=(),
        field_candidates={
            "beta": (
                _candidate(family="mupdf_native"),
                _candidate(family="pdfminer_native"),
            )
        },
    )

    monkeypatch.setattr("veritas.extraction_evidence_runner.parse_pdf_dual", fake_parse)
    monkeypatch.setattr(
        "veritas.extraction_evidence_runner.extract_regression_table",
        lambda snapshots, *, variable_label, locator: bundle,
    )

    output = tmp_path / "predictions.json"
    run = run_extraction_evidence_threshold(
        input_artifact_manifest_path=manifest_path,
        input_artifact_root=input_root,
        review_packet_path=packet_path,
        expected_review_packet_sha256=packet.sha256(),
        target_manifest_path=target_manifest_path,
        paper_artifacts={"doi:10.0000/example": "paper-artifact"},
        threshold_id="nc-010",
        threshold=0.01,
        output_path=output,
    )

    assert parse_calls == [(publication.read_bytes(), "paper-artifact")]
    assert run.split is BenchmarkSplit.DEVELOPMENT
    assert run.targets == 1
    assert run.accepted == 1
    assert run.abstained == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert [row["target_id"] for row in payload["predictions"]] == ["case-1:beta"]
    assert payload["predictions"][0]["resolution"]["decision"] == "accept"


def test_runner_abstains_for_unmapped_target_key(monkeypatch, tmp_path) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    (input_root / "paper.pdf").write_bytes(b"%PDF-1.7\nsynthetic test fixture only\n")
    manifest = build_extraction_input_artifact_manifest(
        input_root,
        (("paper-artifact", "paper.pdf"),),
    )
    manifest_path = tmp_path / "input-manifest.json"
    _write_json(manifest_path, extraction_input_artifact_manifest_payload(manifest))

    packet = _packet(key="ci_lower")
    packet_path = tmp_path / "reviewer-a.review-packet.json"
    _write_json(packet_path, packet.to_payload())
    target_manifest = ExtractionSplitTargetManifest(
        split=BenchmarkSplit.TEST,
        gold_manifest_sha256="d" * 64,
        split_lock_sha256="e" * 64,
        article_family_ids=("doi:10.0000/example",),
        target_ids=("case-1:ci_lower",),
    )
    target_manifest_path = tmp_path / "test-targets.json"
    _write_json(target_manifest_path, target_manifest.to_payload())

    monkeypatch.setattr(
        "veritas.extraction_evidence_runner.parse_pdf_dual",
        lambda pdf_bytes, *, artifact_id: (object(), object()),
    )
    monkeypatch.setattr(
        "veritas.extraction_evidence_runner.extract_regression_table",
        lambda snapshots, *, variable_label, locator: SimpleNamespace(
            ambiguities=(),
            field_candidates={},
        ),
    )

    run = run_extraction_evidence_threshold(
        input_artifact_manifest_path=manifest_path,
        input_artifact_root=input_root,
        review_packet_path=packet_path,
        expected_review_packet_sha256=packet.sha256(),
        target_manifest_path=target_manifest_path,
        paper_artifacts={"doi:10.0000/example": "paper-artifact"},
        threshold_id="nc-020",
        threshold=0.02,
        output_path=tmp_path / "predictions.json",
    )
    assert run.accepted == 0
    assert run.abstained == 1
