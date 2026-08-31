from __future__ import annotations

from dataclasses import replace

import pytest

from veritas.audit import AuditEngine
from veritas.benchmark import (
    BenchmarkCase,
    BenchmarkSplit,
    PaperAuditOutcome,
    issue_production_calibration_certificate,
)
from veritas.claims import ArtifactRef
from veritas.extraction import (
    ConformalCalibration,
    ConformalExtractionGate,
    ExtractionCandidate,
)
from veritas.ingestion import (
    CalibrationScope,
    EvidenceKind,
    EvidenceLedger,
    IngestionProtocol,
    ObjectDraft,
    PromotionDecision,
    PromotionSpec,
    ResolvedEvidence,
)
from veritas.models import RegressionResult, ReportedNumber, SourceLocation

_CALIBRATION_SHA = "b" * 64
_DEFAULT_ENGINE = AuditEngine()
_CERT_CASES = [
    BenchmarkCase(
        case_id=f"clean-case-{i}",
        paper_id=f"clean-{i}",
        corruption_family="none",
        expected_material_issue=False,
        split=BenchmarkSplit.TEST,
        metadata={},
    )
    for i in range(400)
]
_CERT_CASES.extend(
    BenchmarkCase(
        case_id=f"positive-case-{i}",
        paper_id=f"positive-{i}",
        corruption_family="p_value_override",
        expected_material_issue=True,
        split=BenchmarkSplit.TEST,
        metadata={},
    )
    for i in range(100)
)
_CERT_OUTCOMES = [PaperAuditOutcome(f"clean-{i}", False, False) for i in range(400)]
_CERT_OUTCOMES.extend(PaperAuditOutcome(f"positive-{i}", True, True) for i in range(100))
_CERT_REPORT, _PRODUCTION_CERTIFICATE = issue_production_calibration_certificate(
    calibration_sha256=_CALIBRATION_SHA,
    audited_system_sha256=_DEFAULT_ENGINE.manifest_sha256(),
    cases=_CERT_CASES,
    outcomes=_CERT_OUTCOMES,
)
assert _CERT_REPORT.certified and _PRODUCTION_CERTIFICATE is not None


def _protocol(*, scope: CalibrationScope = CalibrationScope.PRODUCTION_CERTIFIED) -> IngestionProtocol:
    return IngestionProtocol(
        protocol_id="pdf-paper-only",
        protocol_version="0.10.0",
        object_schema_version="regression-v1",
        calibration_sha256=_CALIBRATION_SHA,
        parser_versions=(("native", "1.2.0"), ("vlm", "2026-08")),
        calibration_scope=scope,
        production_certificate=(
            _PRODUCTION_CERTIFICATE
            if scope is CalibrationScope.PRODUCTION_CERTIFIED
            else None
        ),
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


def _ledger(
    *,
    with_hash: bool = True,
    draft: ObjectDraft | None = None,
    scope: CalibrationScope = CalibrationScope.PRODUCTION_CERTIFIED,
) -> EvidenceLedger:
    ledger = EvidenceLedger(
        artifact=ArtifactRef(
            artifact_id="paper",
            kind="pdf",
            sha256="a" * 64 if with_hash else None,
            uri="https://example.invalid/paper.pdf",
        ),
        protocol=_protocol(scope=scope),
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


def test_production_scope_requires_heldout_certificate():
    with pytest.raises(ValueError, match="held-out production certificate"):
        IngestionProtocol(
            protocol_id="pdf-paper-only",
            protocol_version="0.10.0",
            object_schema_version="regression-v1",
            calibration_sha256=_CALIBRATION_SHA,
            parser_versions=(("native", "1.2.0"), ("vlm", "2026-08")),
            calibration_scope=CalibrationScope.PRODUCTION_CERTIFIED,
        )


def test_production_certificate_must_match_protocol_calibration():
    mismatched = replace(_PRODUCTION_CERTIFICATE, calibration_sha256="c" * 64)
    with pytest.raises(ValueError, match="does not match protocol calibration"):
        IngestionProtocol(
            protocol_id="pdf-paper-only",
            protocol_version="0.10.0",
            object_schema_version="regression-v1",
            calibration_sha256=_CALIBRATION_SHA,
            parser_versions=(("native", "1.2.0"), ("vlm", "2026-08")),
            calibration_scope=CalibrationScope.PRODUCTION_CERTIFIED,
            production_certificate=mismatched,
        )


def test_precisely_sourced_production_calibration_is_hard_audit_ready():
    report, envelope = _ledger().promote("reg-1", _spec(), _builder)
    assert report.decision is PromotionDecision.PROMOTE
    assert report.detector_ready
    assert report.hard_audit_ready
    assert report.calibration_scope is CalibrationScope.PRODUCTION_CERTIFIED
    assert report.production_certificate_sha256 == _PRODUCTION_CERTIFICATE.sha256()
    assert report.certified_system_sha256 == _DEFAULT_ENGINE.manifest_sha256()
    assert envelope is not None
    assert envelope.production_authorized
    assert envelope.artifact_sha256 == "a" * 64
    assert len(envelope.protocol_sha256) == 64
    assert len(envelope.evidence_sha256) == 64


def test_benchmark_calibration_can_enter_detector_but_not_gain_production_authority():
    report, envelope = _ledger(scope=CalibrationScope.BENCHMARK).promote("reg-1", _spec(), _builder)
    assert report.decision is PromotionDecision.PROMOTE
    assert report.detector_ready
    assert not report.hard_audit_ready
    assert envelope is not None
    assert not envelope.production_authorized

    summary = AuditEngine().audit_verified([envelope])
    assert summary.findings
    finding = next(finding for finding in summary.findings if finding.grade.value >= 3)
    provenance = finding.evidence["ingestion_provenance"]
    assert provenance["calibration_scope"] == CalibrationScope.BENCHMARK.value
    assert provenance["production_certificate_sha256"] is None
    assert provenance["production_hard_finding_authorized"] is False

    with pytest.raises(ValueError, match="held-out certificate"):
        AuditEngine().audit_production_verified([envelope])


def test_missing_artifact_hash_blocks_detector_promotion():
    report, envelope = _ledger(with_hash=False).promote("reg-1", _spec(), _builder)
    assert report.decision is PromotionDecision.UNVERIFIABLE
    assert not report.detector_ready
    assert envelope is None
    assert any("no content SHA-256" in reason for reason in report.reasons)


def test_imprecise_source_anchor_blocks_detector_promotion():
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


def test_production_verified_audit_binds_certificate_and_system_to_e3_finding():
    report, envelope = _ledger().promote("reg-1", _spec(), _builder)
    assert report.hard_audit_ready and envelope is not None
    summary = AuditEngine().audit_production_verified([envelope])
    assert summary.findings
    finding = next(finding for finding in summary.findings if finding.grade.value >= 3)
    provenance = finding.evidence["ingestion_provenance"]
    assert provenance["artifact_sha256"] == "a" * 64
    assert provenance["ingestion_protocol_sha256"] == envelope.protocol_sha256
    assert provenance["promotion_spec_sha256"] == envelope.promotion_spec_sha256
    assert provenance["extraction_evidence_sha256"] == envelope.evidence_sha256
    assert provenance["calibration_scope"] == CalibrationScope.PRODUCTION_CERTIFIED.value
    assert provenance["production_certificate_sha256"] == _PRODUCTION_CERTIFICATE.sha256()
    assert provenance["certified_system_sha256"] == _DEFAULT_ENGINE.manifest_sha256()
    assert provenance["executed_system_sha256"] == _DEFAULT_ENGINE.manifest_sha256()
    assert provenance["production_hard_finding_authorized"] is True


def test_production_certificate_cannot_authorize_a_different_detector_system():
    report, envelope = _ledger().promote("reg-1", _spec(), _builder)
    assert report.hard_audit_ready and envelope is not None
    changed_engine = AuditEngine(include_experimental=True)
    assert changed_engine.manifest_sha256() != _DEFAULT_ENGINE.manifest_sha256()
    with pytest.raises(ValueError, match="different detector/numerical system manifest"):
        changed_engine.audit_production_verified([envelope])


def test_research_verified_audit_never_confers_production_authority_even_with_certificate():
    report, envelope = _ledger().promote("reg-1", _spec(), _builder)
    assert report.hard_audit_ready and envelope is not None
    summary = AuditEngine().audit_verified([envelope])
    finding = next(finding for finding in summary.findings if finding.grade.value >= 3)
    provenance = finding.evidence["ingestion_provenance"]
    assert provenance["calibration_scope"] == CalibrationScope.PRODUCTION_CERTIFIED.value
    assert provenance["production_certificate_sha256"] == _PRODUCTION_CERTIFICATE.sha256()
    assert provenance["production_hard_finding_authorized"] is False


def test_protocol_hash_changes_with_calibration_scope_and_certificate():
    production = _protocol(scope=CalibrationScope.PRODUCTION_CERTIFIED)
    benchmark = _protocol(scope=CalibrationScope.BENCHMARK)
    assert production.sha256() != benchmark.sha256()
    assert production.production_certificate_sha256 == _PRODUCTION_CERTIFICATE.sha256()
    assert benchmark.production_certificate_sha256 is None


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
