from veritas.extraction import (
    ConformalCalibration,
    ConformalExtractionGate,
    ExtractionCandidate,
)
from veritas.extraction_benchmark import (
    ExtractionGoldTarget,
    ExtractionPrediction,
    evaluate_extraction_benchmark,
)
from veritas.ingestion import EvidenceKind
from veritas.models import SourceLocation


def _gate() -> ConformalExtractionGate:
    return ConformalExtractionGate(ConformalCalibration((0.01, 0.02, 0.03, 0.04, 0.05), alpha=0.2))


def _source(*, page: int = 5, row: str = "Treatment", table: str = "2") -> SourceLocation:
    return SourceLocation(artifact_id="paper", page=page, table=table, row=row, column="Estimate")


def _gold(
    target_id: str,
    family: str,
    value: str,
    *,
    critical: bool = True,
    kind: EvidenceKind = EvidenceKind.FIELD,
    key: str = "beta",
    source: SourceLocation | None = None,
) -> ExtractionGoldTarget:
    return ExtractionGoldTarget(
        target_id=target_id,
        paper_id=f"paper-{family}",
        article_family_id=family,
        object_type="RegressionResult",
        key=key,
        kind=kind,
        accepted_normalized_values=(value,),
        source=source or _source(),
        critical_for_hard_audit=critical,
        reviewers=("reviewer-a", "reviewer-b"),
        adjudicated=True,
    )


def _prediction(target_id: str, value: str, *, source: SourceLocation | None = None) -> ExtractionPrediction:
    source = source or _source()
    resolution = _gate().resolve(
        [
            ExtractionCandidate("native", "native_pdf", value, value, 0.02, source),
            ExtractionCandidate("vlm", "vision_language", value, value, 0.03, source),
        ]
    )
    return ExtractionPrediction(target_id=target_id, resolution=resolution)


def test_correct_accept_requires_both_value_and_source_identity():
    gold = [_gold("good", "fam-a", "0.18"), _gold("wrong-source", "fam-b", "0.22")]
    predictions = [
        _prediction("good", "0.18"),
        _prediction("wrong-source", "0.22", source=_source(page=7)),
    ]
    report = evaluate_extraction_benchmark(gold, predictions)
    assert report.accepted == 2
    assert report.fully_correct_accepts == 1
    assert report.wrong_accepts == 1
    assert report.accepted_full_accuracy == 0.5
    assert report.accepted_value_accuracy == 1.0
    assert report.accepted_source_accuracy == 0.5


def test_same_value_wrong_row_is_visible_in_table_row_identity_metric():
    gold = [
        _gold("correct", "fam-a", "0.18"),
        _gold("wrong-row", "fam-b", "0.18"),
    ]
    predictions = [
        _prediction("correct", "0.18"),
        _prediction("wrong-row", "0.18", source=_source(row="Control")),
    ]
    report = evaluate_extraction_benchmark(gold, predictions)
    assert report.accepted_field_value_accuracy == 1.0
    assert report.table_row_targets == 2
    assert report.accepted_table_row_targets == 2
    assert report.accepted_table_row_identity_accuracy == 0.5
    wrong = next(outcome for outcome in report.outcomes if outcome.target_id == "wrong-row")
    assert wrong.value_correct is True
    assert wrong.display_item_correct is True
    assert wrong.row_correct is False
    assert wrong.source_correct is False


def test_semantic_gate_accuracy_is_reported_separately_from_numeric_fields():
    methods_source = SourceLocation(
        artifact_id="paper",
        page=9,
        section="Methods",
        text_quote="Inference uses a normal approximation.",
    )
    gold = [
        _gold("beta", "fam-a", "0.18"),
        _gold(
            "inference",
            "fam-a",
            "normal",
            kind=EvidenceKind.SEMANTIC_GATE,
            key="inference_distribution",
            source=methods_source,
        ),
    ]
    predictions = [
        _prediction("beta", "0.18"),
        _prediction("inference", "student_t", source=methods_source),
    ]
    report = evaluate_extraction_benchmark(gold, predictions)
    assert report.field_targets == 1
    assert report.accepted_field_value_accuracy == 1.0
    assert report.semantic_gate_targets == 1
    assert report.accepted_semantic_gate_targets == 1
    assert report.accepted_semantic_gate_accuracy == 0.0


def test_missing_prediction_counts_as_abstention_not_wrong_accept():
    report = evaluate_extraction_benchmark([_gold("missing", "fam-a", "0.18")], [])
    assert report.accepted == 0
    assert report.abstentions == 1
    assert report.wrong_accepts == 0


def test_article_family_risk_is_not_diluted_by_many_easy_fields():
    gold = []
    predictions = []
    for index in range(20):
        target_id = f"fam-a-{index}"
        gold.append(_gold(target_id, "fam-a", "0.18"))
        predictions.append(_prediction(target_id, "0.18" if index else "0.81"))
    gold.append(_gold("fam-b", "fam-b", "0.25"))
    predictions.append(_prediction("fam-b", "0.25"))

    report = evaluate_extraction_benchmark(gold, predictions)
    assert report.targets == 21
    assert report.wrong_accepts == 1
    assert report.critical_article_families == 2
    assert report.critical_wrong_accept_families == 1
    assert report.critical_family_wrong_accept_rate == 0.5
    assert report.critical_family_wrong_accept_upper_bound >= 0.5


def test_noncritical_wrong_accept_does_not_contaminate_critical_family_metric():
    gold = [
        _gold("critical", "fam-a", "0.18", critical=True),
        _gold("noncritical", "fam-a", "0.30", critical=False),
    ]
    predictions = [_prediction("critical", "0.18"), _prediction("noncritical", "0.03")]
    report = evaluate_extraction_benchmark(gold, predictions)
    assert report.wrong_accepts == 1
    assert report.critical_wrong_accept_families == 0
    assert report.critical_family_wrong_accept_rate == 0.0
