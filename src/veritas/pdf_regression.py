from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from .claims import ArtifactRef
from .extraction import ConformalExtractionGate, ExtractionCandidate
from .ingestion import (
    EvidenceKind,
    EvidenceLedger,
    IngestionProtocol,
    ObjectDraft,
    PromotionSpec,
    ResolvedEvidence,
)
from .models import RegressionResult, ReportedNumber, SourceLocation
from .pdf_native import NativePDFSnapshot, PDFTable, parse_pdf_dual
from .types import ComparisonOperator, Materiality

_NUMBER_RE = re.compile(
    r"^\s*(?P<op><=|>=|<|>)?\s*(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(?:\*+)?\s*$"
)
_HEADER_CLEAN_RE = re.compile(r"[^a-z0-9]+")

_HEADER_ALIASES = {
    "variable": {"variable", "variables", "term", "predictor", "predictors", "regressor", "regressors"},
    "beta": {"b", "beta", "coef", "coefficient", "estimate"},
    "se": {"se", "stderr", "standarderror", "stddev", "stdse"},
    "t_stat": {
        "t",
        "tstat",
        "tstatistic",
        "tvalue",
        "z",
        "zstat",
        "zstatistic",
        "zvalue",
    },
    "p_value": {"p", "pvalue", "probz", "probt"},
}

_SIGN_TRANSLATION = str.maketrans({
    "−": "-",  # U+2212 mathematical minus
    "–": "-",  # en dash sometimes substituted by PDF text extraction
    "—": "-",  # em dash, tolerated only inside otherwise numeric cells
    "﹣": "-",
    "－": "-",
    "＋": "+",
    "≤": "<=",
    "≥": ">=",
})


def _normalized_header(value: str | None) -> str:
    if value is None:
        return ""
    return _HEADER_CLEAN_RE.sub("", value.casefold())


def _header_role(value: str | None) -> str | None:
    normalized = _normalized_header(value)
    for role, aliases in _HEADER_ALIASES.items():
        if normalized in aliases:
            return role
    return None


def _normalize_numeric_text(raw: str) -> str:
    return raw.translate(_SIGN_TRANSLATION).replace("\u00a0", " ").strip()


def _display_decimals(raw_number: str) -> int | None:
    mantissa = raw_number.lower().split("e", 1)[0]
    if "." not in mantissa:
        return 0
    return len(mantissa.split(".", 1)[1])


def parse_reported_number(raw: str) -> ReportedNumber:
    normalized_raw = _normalize_numeric_text(raw)
    match = _NUMBER_RE.match(normalized_raw)
    if match is None:
        raise ValueError(f"not a supported reported number: {raw!r}")
    operator_raw = match.group("op")
    operator = {
        None: ComparisonOperator.EQ,
        "<": ComparisonOperator.LT,
        "<=": ComparisonOperator.LE,
        ">": ComparisonOperator.GT,
        ">=": ComparisonOperator.GE,
    }[operator_raw]
    number = match.group("number")
    return ReportedNumber(
        value=float(number),
        decimals=_display_decimals(number),
        operator=operator,
    )


def _canonical_number(raw: str) -> str:
    normalized_raw = _normalize_numeric_text(raw)
    number = parse_reported_number(normalized_raw)
    operator = "" if number.operator is ComparisonOperator.EQ else number.operator.value
    decimals = 0 if number.decimals is None else number.decimals
    if "e" in normalized_raw.casefold():
        rendered = format(number.value, ".15g")
    else:
        rendered = f"{number.value:.{decimals}f}"
    return f"{operator}{rendered}"


@dataclass(frozen=True)
class RegressionTableMatch:
    snapshot: NativePDFSnapshot
    table: PDFTable
    header_row_index: int
    data_row_index: int
    columns: dict[str, int]
    variable_text: str

    def source_for(self, raw: str) -> SourceLocation:
        return SourceLocation(
            artifact_id=self.snapshot.artifact_id,
            page=self.table.page,
            table=f"native-{self.table.table_index}",
            row=self.variable_text,
            bbox=self.table.bbox,
            text_quote=raw,
        )


@dataclass(frozen=True)
class RegressionExtractionBundle:
    artifact_id: str
    artifact_sha256: str
    parser_versions: tuple[tuple[str, str], ...]
    field_candidates: dict[str, tuple[ExtractionCandidate, ...]]
    semantic_candidates: dict[str, tuple[ExtractionCandidate, ...]]
    source: SourceLocation


def _find_header(table: PDFTable) -> tuple[int, dict[str, int]] | None:
    for row_index, row in enumerate(table.rows[:5]):
        columns: dict[str, int] = {}
        for column_index, cell in enumerate(row):
            role = _header_role(cell)
            if role is not None and role not in columns:
                columns[role] = column_index
        if {"variable", "beta", "se", "t_stat"}.issubset(columns):
            return row_index, columns
    return None


def _find_match(snapshot: NativePDFSnapshot, variable_label: str) -> RegressionTableMatch | None:
    target = " ".join(variable_label.casefold().split())
    for table in snapshot.tables:
        header = _find_header(table)
        if header is None:
            continue
        header_index, columns = header
        variable_column = columns["variable"]
        for row_index in range(header_index + 1, len(table.rows)):
            row = table.rows[row_index]
            if variable_column >= len(row) or row[variable_column] is None:
                continue
            variable_text = " ".join(str(row[variable_column]).casefold().split())
            if variable_text == target:
                return RegressionTableMatch(snapshot, table, header_index, row_index, columns, str(row[variable_column]))
    return None


def _candidate(match: RegressionTableMatch, key: str, raw: str, normalized: str) -> ExtractionCandidate:
    header_penalty = 0.0 if key in match.columns else 0.02
    table_penalty = 0.0 if len(match.table.rows) >= 2 else 0.02
    return ExtractionCandidate(
        parser_id=match.snapshot.parser_id,
        parser_family=match.snapshot.parser_family,
        raw=raw,
        normalized_value=normalized,
        nonconformity_score=0.01 + header_penalty + table_penalty,
        source=match.source_for(raw),
    )


def extract_regression_table(
    snapshots: tuple[NativePDFSnapshot, ...],
    *,
    variable_label: str,
) -> RegressionExtractionBundle:
    if not snapshots:
        raise ValueError("at least one parser snapshot is required")
    artifact_ids = {snapshot.artifact_id for snapshot in snapshots}
    artifact_hashes = {snapshot.artifact_sha256 for snapshot in snapshots}
    if len(artifact_ids) != 1 or len(artifact_hashes) != 1:
        raise ValueError("all parser snapshots must refer to the same source artifact")

    fields: dict[str, list[ExtractionCandidate]] = {"beta": [], "se": [], "t_stat": [], "p_value": []}
    semantics: dict[str, list[ExtractionCandidate]] = {"inference_distribution": []}
    canonical_source: SourceLocation | None = None

    for snapshot in snapshots:
        match = _find_match(snapshot, variable_label)
        if match is None:
            continue
        row = match.table.rows[match.data_row_index]
        canonical_source = canonical_source or SourceLocation(
            artifact_id=snapshot.artifact_id,
            page=match.table.page,
            table=f"native-{match.table.table_index}",
            row=match.variable_text,
            bbox=match.table.bbox,
            text_quote=match.table.text,
        )
        for key in ("beta", "se", "t_stat", "p_value"):
            column_index = match.columns.get(key)
            if column_index is None or column_index >= len(row) or row[column_index] is None:
                continue
            raw = str(row[column_index])
            try:
                normalized = _canonical_number(raw)
            except ValueError:
                continue
            fields[key].append(_candidate(match, key, raw, normalized))

        stat_header = match.table.rows[match.header_row_index][match.columns["t_stat"]]
        normalized_header = _normalized_header(stat_header)
        if normalized_header in {"z", "zstat", "zstatistic", "zvalue"}:
            semantics["inference_distribution"].append(_candidate(match, "t_stat", str(stat_header), "normal"))

    source = canonical_source or SourceLocation(artifact_id=next(iter(artifact_ids)))
    return RegressionExtractionBundle(
        artifact_id=next(iter(artifact_ids)),
        artifact_sha256=next(iter(artifact_hashes)),
        parser_versions=tuple(sorted((snapshot.parser_id, snapshot.parser_version) for snapshot in snapshots)),
        field_candidates={key: tuple(value) for key, value in fields.items()},
        semantic_candidates={key: tuple(value) for key, value in semantics.items()},
        source=source,
    )


def regression_promotion_spec(*, require_p_value: bool = True) -> PromotionSpec:
    fields = ("beta", "se", "t_stat", "p_value") if require_p_value else ("beta", "se", "t_stat")
    return PromotionSpec(
        object_type="regression_result",
        required_fields=fields,
        critical_semantic_gates=("inference_distribution",),
        min_extraction_confidence=0.98,
        min_independent_parser_families=2,
        require_page_anchor=True,
        require_location_anchor=True,
        spec_version="regression-native-table-v2",
    )


def bundle_to_ledger(
    bundle: RegressionExtractionBundle,
    gate: ConformalExtractionGate,
    *,
    calibration_sha256: str,
    object_id: str,
    extraction_confidence: float = 0.995,
) -> EvidenceLedger:
    protocol = IngestionProtocol(
        protocol_id="dual-native-pdf-regression",
        protocol_version="0.9.0",
        object_schema_version="regression-native-table-v2",
        calibration_sha256=calibration_sha256,
        parser_versions=bundle.parser_versions,
        policy_note="PyMuPDF and pdfplumber must independently support all hard-audit fields and explicit z-inference semantics.",
    )
    ledger = EvidenceLedger(
        artifact=ArtifactRef(
            artifact_id=bundle.artifact_id,
            kind="paper_pdf",
            sha256=bundle.artifact_sha256,
        ),
        protocol=protocol,
    )
    fields: dict[str, ResolvedEvidence] = {}
    for key, candidates in bundle.field_candidates.items():
        if not candidates:
            continue
        resolution = gate.resolve(candidates)
        fields[key] = ResolvedEvidence(
            key=key,
            kind=EvidenceKind.FIELD,
            value=resolution.normalized_value,
            resolution=resolution,
            extraction_confidence=extraction_confidence,
            evidence_note=f"Dual native table extraction for {key}.",
        )
    semantics: dict[str, ResolvedEvidence] = {}
    for key, candidates in bundle.semantic_candidates.items():
        if not candidates:
            continue
        resolution = gate.resolve(candidates)
        semantics[key] = ResolvedEvidence(
            key=key,
            kind=EvidenceKind.SEMANTIC_GATE,
            value=resolution.normalized_value,
            resolution=resolution,
            extraction_confidence=extraction_confidence,
            evidence_note="Inference distribution inferred only from an explicit z-statistic column header.",
        )
    ledger.add_draft(
        ObjectDraft(
            draft_id=object_id,
            object_type="regression_result",
            artifact_id=bundle.artifact_id,
            fields=fields,
            semantic_gates=semantics,
            source=bundle.source,
        )
    )
    return ledger


def _reported_from_scalar(value: object) -> ReportedNumber:
    if not isinstance(value, str):
        raise TypeError("promoted regression numeric fields must be normalized strings")
    return parse_reported_number(value)


def regression_result_builder(
    fields: dict[str, object],
    semantics: dict[str, object],
    draft: ObjectDraft,
) -> RegressionResult:
    distribution = semantics.get("inference_distribution")
    if distribution != "normal":
        raise ValueError("v0.9 native regression builder currently supports explicit z/normal inference only")
    return RegressionResult(
        object_id=draft.draft_id,
        beta=_reported_from_scalar(fields["beta"]),
        se=_reported_from_scalar(fields["se"]),
        t_stat=_reported_from_scalar(fields["t_stat"]),
        p_value=_reported_from_scalar(fields["p_value"]) if "p_value" in fields else None,
        inference_distribution="normal",
        materiality=Materiality.SECONDARY_RESULT,
        source=draft.source,
    )


def prepare_regression_pdf_audit(
    pdf_bytes: bytes,
    gate: ConformalExtractionGate,
    *,
    variable_label: str,
    calibration_sha256: str,
    artifact_id: str = "paper",
    object_id: str = "regression-1",
) -> tuple[EvidenceLedger, PromotionSpec]:
    snapshots = parse_pdf_dual(pdf_bytes, artifact_id=artifact_id)
    bundle = extract_regression_table(snapshots, variable_label=variable_label)
    ledger = bundle_to_ledger(
        bundle,
        gate,
        calibration_sha256=calibration_sha256,
        object_id=object_id,
    )
    return ledger, regression_promotion_spec()


def calibration_manifest_sha256(payload: bytes) -> str:
    return sha256(payload).hexdigest()
