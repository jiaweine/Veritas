from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum

from .models import ReportedNumber, SourceLocation

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PublicationObjectMatchDecision(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class PublicationTableSignature:
    object_id: str
    row_labels: tuple[str, ...]
    column_labels: tuple[str, ...]
    cells: tuple[tuple[ReportedNumber | None, ...], ...]
    source: SourceLocation
    artifact_sha256: str

    def __post_init__(self) -> None:
        _validate_table_shape(self.row_labels, self.column_labels, self.cells)
        _validate_sha256(self.artifact_sha256, label="publication artifact_sha256")


@dataclass(frozen=True)
class GeneratedTableSignature:
    row_labels: tuple[str, ...]
    column_labels: tuple[str, ...]
    cells: tuple[tuple[float | None, ...], ...]
    output_artifact_sha256: str

    def __post_init__(self) -> None:
        _validate_table_shape(self.row_labels, self.column_labels, self.cells)
        _validate_sha256(self.output_artifact_sha256, label="generated output_artifact_sha256")
        for row in self.cells:
            for value in row:
                if value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError("generated table cells must be finite numbers or null")
                if not math.isfinite(float(value)):
                    raise ValueError("generated table cells must be finite")


@dataclass(frozen=True)
class PublicationFigureSignature:
    object_id: str
    panel_labels: tuple[str, ...]
    semantic_series_sha256: str
    source: SourceLocation
    artifact_sha256: str

    def __post_init__(self) -> None:
        _validate_labels(self.panel_labels, label="publication figure panel labels")
        _validate_sha256(self.semantic_series_sha256, label="publication semantic_series_sha256")
        _validate_sha256(self.artifact_sha256, label="publication artifact_sha256")


@dataclass(frozen=True)
class GeneratedFigureSignature:
    panel_labels: tuple[str, ...]
    semantic_series_sha256: str
    output_artifact_sha256: str

    def __post_init__(self) -> None:
        _validate_labels(self.panel_labels, label="generated figure panel labels")
        _validate_sha256(self.semantic_series_sha256, label="generated semantic_series_sha256")
        _validate_sha256(self.output_artifact_sha256, label="generated output_artifact_sha256")


@dataclass(frozen=True)
class PublicationObjectMatch:
    object_id: str
    decision: PublicationObjectMatchDecision
    comparable_cells: int
    matched_cells: int
    mismatched_cells: int
    missing_cells: int
    publication_source: SourceLocation
    publication_artifact_sha256: str
    generated_output_artifact_sha256: str
    reasons: tuple[str, ...] = ()

    @property
    def coverage(self) -> float:
        return (
            (self.matched_cells + self.mismatched_cells) / self.comparable_cells
            if self.comparable_cells
            else 0.0
        )


def match_generated_table(
    publication: PublicationTableSignature,
    generated: GeneratedTableSignature,
    *,
    absolute_tolerance: float = 1e-10,
) -> PublicationObjectMatch:
    if absolute_tolerance < 0.0:
        raise ValueError("absolute_tolerance must be non-negative")
    if publication.row_labels != generated.row_labels:
        return _structural_mismatch(publication, generated.output_artifact_sha256, "row labels differ")
    if publication.column_labels != generated.column_labels:
        return _structural_mismatch(publication, generated.output_artifact_sha256, "column labels differ")

    comparable = matched = mismatched = missing = 0
    for expected_row, observed_row in zip(publication.cells, generated.cells, strict=True):
        for expected, observed in zip(expected_row, observed_row, strict=True):
            if expected is None:
                continue
            comparable += 1
            if observed is None:
                missing += 1
                continue
            if _reported_number_matches(expected, float(observed), absolute_tolerance):
                matched += 1
            else:
                mismatched += 1

    if comparable == 0:
        decision = PublicationObjectMatchDecision.UNVERIFIABLE
        reasons = ("publication table contains no comparable numeric cells",)
    elif mismatched or missing:
        decision = PublicationObjectMatchDecision.MISMATCH
        reasons = ()
    else:
        decision = PublicationObjectMatchDecision.MATCH
        reasons = ()
    return PublicationObjectMatch(
        object_id=publication.object_id,
        decision=decision,
        comparable_cells=comparable,
        matched_cells=matched,
        mismatched_cells=mismatched,
        missing_cells=missing,
        publication_source=publication.source,
        publication_artifact_sha256=publication.artifact_sha256,
        generated_output_artifact_sha256=generated.output_artifact_sha256,
        reasons=reasons,
    )


def match_generated_figure(
    publication: PublicationFigureSignature,
    generated: GeneratedFigureSignature,
) -> PublicationObjectMatch:
    reasons: list[str] = []
    if publication.panel_labels != generated.panel_labels:
        reasons.append("figure panel labels differ")
    if publication.semantic_series_sha256 != generated.semantic_series_sha256:
        reasons.append("figure semantic data-series identity differs")
    decision = (
        PublicationObjectMatchDecision.MATCH
        if not reasons
        else PublicationObjectMatchDecision.MISMATCH
    )
    return PublicationObjectMatch(
        object_id=publication.object_id,
        decision=decision,
        comparable_cells=1,
        matched_cells=1 if not reasons else 0,
        mismatched_cells=0 if not reasons else 1,
        missing_cells=0,
        publication_source=publication.source,
        publication_artifact_sha256=publication.artifact_sha256,
        generated_output_artifact_sha256=generated.output_artifact_sha256,
        reasons=tuple(reasons),
    )


def _reported_number_matches(
    expected: ReportedNumber,
    observed: float,
    tolerance: float,
) -> bool:
    low, high = expected.rounding_interval()
    return low - tolerance <= observed <= high + tolerance


def _structural_mismatch(
    publication: PublicationTableSignature,
    output_sha256: str,
    reason: str,
) -> PublicationObjectMatch:
    comparable = sum(cell is not None for row in publication.cells for cell in row)
    return PublicationObjectMatch(
        object_id=publication.object_id,
        decision=PublicationObjectMatchDecision.MISMATCH,
        comparable_cells=comparable,
        matched_cells=0,
        mismatched_cells=0,
        missing_cells=comparable,
        publication_source=publication.source,
        publication_artifact_sha256=publication.artifact_sha256,
        generated_output_artifact_sha256=output_sha256,
        reasons=(reason,),
    )


def _validate_table_shape(row_labels, column_labels, cells) -> None:
    _validate_labels(row_labels, label="table row labels")
    _validate_labels(column_labels, label="table column labels")
    if len(cells) != len(row_labels):
        raise ValueError("table cell rows must match row labels")
    if any(len(row) != len(column_labels) for row in cells):
        raise ValueError("table cell columns must match column labels")


def _validate_labels(labels: tuple[str, ...], *, label: str) -> None:
    if not labels:
        raise ValueError(f"{label} must be non-empty")
    if any(not isinstance(value, str) or not value.strip() for value in labels):
        raise ValueError(f"{label} must contain non-empty strings")
    if len(set(labels)) != len(labels):
        raise ValueError(f"{label} must be unique")


def _validate_sha256(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")
