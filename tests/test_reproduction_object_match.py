from __future__ import annotations

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction_object_match import (
    GeneratedFigureSignature,
    GeneratedTableSignature,
    PublicationFigureSignature,
    PublicationObjectMatchDecision,
    PublicationTableSignature,
    match_generated_figure,
    match_generated_table,
)
from veritas.types import ComparisonOperator


def test_generated_table_matches_rounding_compatible_publication_cells() -> None:
    publication = PublicationTableSignature(
        "table-3",
        ("Treatment", "Constant"),
        ("B", "SE"),
        (
            (ReportedNumber(0.12, decimals=2), ReportedNumber(0.03, decimals=2)),
            (ReportedNumber(1.00, decimals=2), None),
        ),
        SourceLocation(artifact_id="paper", page=8, table="Table 3"),
        "a" * 64,
    )
    generated = GeneratedTableSignature(
        ("Treatment", "Constant"),
        ("B", "SE"),
        ((0.124, 0.034), (1.004, None)),
        "b" * 64,
    )

    result = match_generated_table(publication, generated)

    assert result.decision is PublicationObjectMatchDecision.MATCH
    assert result.comparable_cells == 3
    assert result.matched_cells == 3
    assert result.coverage == 1.0


def test_generated_table_honors_reported_inequality_cells() -> None:
    publication = PublicationTableSignature(
        "table-3",
        ("Treatment",),
        ("p",),
        ((ReportedNumber(0.001, operator=ComparisonOperator.LT),),),
        SourceLocation(artifact_id="paper", page=8, table="Table 3"),
        "a" * 64,
    )
    matching = GeneratedTableSignature(
        ("Treatment",),
        ("p",),
        ((0.0004,),),
        "b" * 64,
    )
    wrong = GeneratedTableSignature(
        ("Treatment",),
        ("p",),
        ((0.02,),),
        "c" * 64,
    )

    assert match_generated_table(publication, matching).decision is PublicationObjectMatchDecision.MATCH
    assert match_generated_table(publication, wrong).decision is PublicationObjectMatchDecision.MISMATCH


def test_generated_table_rejects_wrong_row_identity_before_numeric_match() -> None:
    publication = PublicationTableSignature(
        "table-3",
        ("Treatment",),
        ("B",),
        ((ReportedNumber(0.12, decimals=2),),),
        SourceLocation(artifact_id="paper", page=8, table="Table 3"),
        "a" * 64,
    )
    generated = GeneratedTableSignature(
        ("Placebo",),
        ("B",),
        ((0.12,),),
        "b" * 64,
    )

    result = match_generated_table(publication, generated)

    assert result.decision is PublicationObjectMatchDecision.MISMATCH
    assert result.reasons == ("row labels differ",)


def test_generated_table_marks_missing_publication_cell_as_mismatch() -> None:
    publication = PublicationTableSignature(
        "table-3",
        ("Treatment",),
        ("B",),
        ((ReportedNumber(0.12, decimals=2),),),
        SourceLocation(artifact_id="paper", page=8, table="Table 3"),
        "a" * 64,
    )
    generated = GeneratedTableSignature(
        ("Treatment",),
        ("B",),
        ((None,),),
        "b" * 64,
    )

    result = match_generated_table(publication, generated)

    assert result.decision is PublicationObjectMatchDecision.MISMATCH
    assert result.missing_cells == 1


def test_generated_figure_requires_panel_and_semantic_series_identity() -> None:
    publication = PublicationFigureSignature(
        "figure-2",
        ("A", "B"),
        "c" * 64,
        SourceLocation(artifact_id="paper", page=10, figure="Figure 2"),
        "a" * 64,
    )
    matching = GeneratedFigureSignature(("A", "B"), "c" * 64, "d" * 64)
    wrong = GeneratedFigureSignature(("A", "B"), "e" * 64, "f" * 64)

    assert match_generated_figure(publication, matching).decision is PublicationObjectMatchDecision.MATCH
    mismatch = match_generated_figure(publication, wrong)
    assert mismatch.decision is PublicationObjectMatchDecision.MISMATCH
    assert "semantic data-series identity differs" in mismatch.reasons[0]
