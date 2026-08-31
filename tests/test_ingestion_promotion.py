from __future__ import annotations

from veritas.audit import AuditEngine
from veritas.claims import ArtifactRef
from veritas.extraction import (
    ConformalCalibration,
    ConformalExtractionGate,
    ExtractionCandidate,
)
from veritas.ingestion import (
    EvidenceKind,
    EvidenceLedger,
    IngestionProtocol,
    ObjectDraft,
    PromotionDecision,
    PromotionSpec,
    ResolvedEvidence,
)
from veritas.models import RegressionResult, ReportedNumber, SourceLocation


def _protocol() -> IngestionProtocol:
    return IngestionProtocol(
        protocol_id="pdf-paper-only",
        protocol_version="0.8.0",
        object_schema_version="regression-v1",
        calibration_sha256="b" * 64,
        parser_versions=(("native", "1.2.0"), ("vlm", "2026-08")),
    )


def _gate() -> ConformalExtractionGate:
    return ConformalExtractionGate(
        ConformalCalibration((0.01, 0.02, 0.03, 0.04, 0.05), alpha=0.2),
        min_independent_families=2,
    )


def _source(*, precise: bool = True, methods: bool = False) -> SourceLocation:
    if not precise:
        return SourceLocation(artifact_id="paper")
    if methods:
        return SourceLocation(
            artifact_id="paper",
            page=9,
            section="Methods",
            text_quote="Inference uses the normal approximation.",
        )
    return SourceLocation(
        artifact_id="paper",
        page=5,
        table="2",
        row="Treatment",
        column="Estimate",
    )


def _evidence(
    key: str,
    value: object,
    normalized: str,
    *,
    kind: EvidenceKind = EvidenceKind.FIELD,
    confidence: float = 0.995,
    precise: bool = True,
    methods: bool = False,
    conflict: bool = False,
) -> ResolvedEvidence:
    source = _source(precise=precise, methods=methods)
    candidates = [
        ExtractionCandidate("native", "native_pdf", normalized, normalized, 0.02, source),
        ExtractionCandidate(
            "vlm",
            "vision_language",
            "other" if conflict else normalized,
            "other" if conflict else normalized,
            0.03,
            source,
        ),
    ]
    resolution = _gate().resolve(candidates)
    return ResolvedEvidence(
        key=key,
        kind=kind,
        value=value,
        resolution=resolution,
        extraction_confidence=confidence,
    )


def _draft(
    *,
    confidence: float = 0.995,
    precise: bool = True,
    conflict: bool = False,
    include_semantic_gate: bool = True,
) -> ObjectDraft:
    semantic_gates = {}
    if include_semantic_gate:
        semantic_gates["inference_distribution"] = _evidence(
            "inference_distribution",
            "normal",
            "normal",
            kind=EvidenceKind.SEMANTIC_GATE,
            confidence=confidence,
            precise=precise,
            methods=True,
        )
    return ObjectDraft(
        draft_id="reg-1",
        object_type="RegressionResult",
        artifact_id="paper",
        fields={
            "beta": _evidence("beta", 0.18, "0.18", confidence=confidence, precise=precise),
            "se": _evidence("se", 0.05, "0.05", confidence=confidence, precise=precise),
            "p_value": _evidence(
                "p_value",
                0.90,
                "0.90",
                confidence=confidence,
                precise=precise,
                conflict=conflict,
            ),
        },
        semantic_gates=semantic_gates,
        source=_source(precise=precise),
    )


def _spec() -> PromotionSpec:
    return PromotionSpec(
        object_type="RegressionResult",
        required_fields=("beta", "se", "p_value"),
        critical_semantic_gates=("inference_distribution",),
        min_extraction_confidence=0.98,
        min_independent_parser_families=2,
    )


def _ledger(*, with_hash: bool = True, draft: ObjectDraft | None = None) -> EvidenceLedger:
    ledger = EvidenceLedger(
        artifact=ArtifactRef(
            artifact_id="paper",
            kind="pdf",
            sha256="a" * 64 if with_hash else None,
            uri="https://example.invalid/paper.pdf",
        ),
        protocol=_protocol(),
    )
    ledger.add_draft(draft or _draft())
    return ledger


def _builder(fields, semantic, draft):
    return RegressionResult(
        object_id=draft.draft_id,
        beta=ReportedNumber(float(fields["beta"]), decimals=2),
        se=ReportedNumber(float(fields["se"]), decimals=2),
        p_value=ReportedNumber(float(fields["p_value"]), decimals=2),
        inference_distribution=str(semantic["inference_distribution"]),
        source=draft.source,
    )


def test_precisely_sourced_calibrated_object_is_promoted():
    report, envelope = _ledger().promote("reg-1", _spec(), _builder)
    assert report.decision is PromotionDecision.PROMOTE
    assert report.hard_audit_ready
    assert envelope is not None
    assert envelope.artifact_sha256 == "a" * 64
    assert len(envelope.protocol_sha256) == 64
    assert len(envelope.evidence_sha256) == 64


def test_missing_artifact_hash_blocks_hard_audit_promotion():
    report, envelope = _ledger(with_hash=False).promote("reg-1", _spec(), _builder)
    assert report.decision is PromotionDecision.UNVERIFIABLE
    assert envelope is None
    assert any("no content SHA-256" in reason for reason in report.reasons)


def test_imprecise_source_anchor_blocks_hard_audit_promotion():
    report, envelope = _ledger(draft=_draft(precise=False)).promote("reg-1", _spec(), _builder)
    assert report.decision is PromotionDecision.UNVERIFIABLE
    assert envelope is None
    assert any("precise source anchor" in reason for reason in report.reasons)


def test_parser_conflict_routes_object_to_review_not_detector():
    report, envelope = _ledger(draft=_draft(conflict=True)).promote("reg-1", _spec(), _builder)
    assert report.decision is PromotionDecision.REVIEW
    assert envelope is None
    assert any("disagree" in reason for reason in report.reasons)


def test_low_confidence_routes_object_to_review_even_after_conformal_accept():
    report, envelope = _ledger(draft=_draft(confidence=0.90)).promote("reg-1", _spec(), _builder)
    assert report.decision is PromotionDecision.REVIEW
    assert envelope is None
    assert any("below promotion threshold" in reason for reason in report.reasons)


def test_missing_critical_semantic_gate_is_unverifiable():
    report, envelope = _ledger(draft=_draft(include_semantic_gate=False)).promote(
        "reg-1", _spec(), _builder
    )
    assert report.decision is PromotionDecision.UNVERIFIABLE
    assert envelope is None
    assert any("missing critical semantic gate" in reason for reason in report.reasons)


def test_verified_audit_binds_ingestion_hashes_to_e3_finding():
    report, envelope = _ledger().promote("reg-1", _spec(), _builder)
    assert report.hard_audit_ready and envelope is not None
    summary = AuditEngine().audit_verified([envelope])
    assert summary.findings
    finding = next(finding for finding in summary.findings if finding.grade.value >= 3)
    provenance = finding.evidence["ingestion_provenance"]
    assert provenance["artifact_sha256"] == "a" * 64
    assert provenance["ingestion_protocol_sha256"] == envelope.protocol_sha256
    assert provenance["promotion_spec_sha256"] == envelope.promotion_spec_sha256
    assert provenance["extraction_evidence_sha256"] == envelope.evidence_sha256


def test_evidence_hash_is_stable_to_parser_candidate_order():
    source = _source()
    gate = _gate()
    candidates = [
        ExtractionCandidate("native", "native_pdf", "0.18", "0.18", 0.02, source),
        ExtractionCandidate("vlm", "vision_language", "0.18", "0.18", 0.03, source),
    ]
    first = ResolvedEvidence(
        key="beta",
        kind=EvidenceKind.FIELD,
        value=0.18,
        resolution=gate.resolve(candidates),
        extraction_confidence=0.995,
    )
    second = ResolvedEvidence(
        key="beta",
        kind=EvidenceKind.FIELD,
        value=0.18,
        resolution=gate.resolve(list(reversed(candidates))),
        extraction_confidence=0.995,
    )

    def make(item: ResolvedEvidence) -> EvidenceLedger:
        draft = _draft()
        fields = dict(draft.fields)
        fields["beta"] = item
        return _ledger(
            draft=ObjectDraft(
                draft_id=draft.draft_id,
                object_type=draft.object_type,
                artifact_id=draft.artifact_id,
                fields=fields,
                semantic_gates=draft.semantic_gates,
                source=draft.source,
            )
        )

    report_a = make(first).evaluate("reg-1", _spec())
    report_b = make(second).evaluate("reg-1", _spec())
    assert report_a.evidence_sha256 == report_b.evidence_sha256
