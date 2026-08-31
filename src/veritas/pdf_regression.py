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
from .pdf_geometry import reconstruct_borderless_tables
from .pdf_native import NativePDFSnapshot, PDFTable, canonical_table_label, parse_pdf_dual
from .types import ComparisonOperator, Materiality

_NUMBER_RE = re.compile(
    r"^\s*(?P<op><=|>=|<|>)?\s*(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(?:\*+)?\s*$"
)
_HEADER_CLEAN_RE = re.compile(r"[^a-z0-9]+")

_HEADER_ALIASES = {
    "variable": {
        "variable",
        "variables",
        "independentvariable",
        "independentvariables",
        "term",
        "predictor",
        "predictors",
        "regressor",
        "regressors",
    },
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
    # Non-audited columns still act as geometry separators in wide journal tables.
    "separator_wald": {"wald", "waldchi2", "waldx2"},
    "separator_or": {"or", "oddsratio"},
    "separator_ci": {"ci", "confidenceinterval"},
}

_HEADER_SYMBOL_TRANSLATION = str.maketrans(
    {
        "β": "beta",
        "Β": "beta",
    }
)

_SIGN_TRANSLATION = str.maketrans(
    {
        "−": "-",  # U+2212 mathematical minus
        "–": "-",  # en dash sometimes substituted by PDF text extraction
        "—": "-",  # em dash, tolerated only inside otherwise numeric cells
        "﹣": "-",
        "－": "-",
        "＋": "+",
        "≤": "<=",
        "≥": ">=",
    }
)


def _normalized_header(value: str | None) -> str:
    if value is None:
        return ""
    translated = value.translate(_HEADER_SYMBOL_TRANSLATION)
    return _HEADER_CLEAN_RE.sub("", translated.casefold())


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


def _table_source_id(table: PDFTable) -> str:
    if table.table_index < 0:
        return f"word-geometry-v1:{abs(table.table_index)}"
    return f"native-table:{table.table_index}"


def _source_table_label(table: PDFTable) -> str:
    source_id = _table_source_id(table)
    if table.caption:
        return f"{table.caption} [{source_id}]"
    return source_id


def _extraction_mode(table: PDFTable) -> str:
    return "word_geometry_v1" if table.table_index < 0 else "native_table"


@dataclass(frozen=True)
class RegressionLocator:
    """Publication-visible identity constraints for one reported regression row."""

    table_label: str | None = None
    expected_page: int | None = None

    def canonical_table_label(self) -> str | None:
        if self.table_label is None:
            return None
        label = canonical_table_label(self.table_label)
        if label is None:
            raise ValueError(f"unsupported table label: {self.table_label!r}")
        return label


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
            table=_source_table_label(self.table),
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
    ambiguities: tuple[str, ...] = ()


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


def _match_table(
    snapshot: NativePDFSnapshot,
    table: PDFTable,
    *,
    target: str,
) -> RegressionTableMatch | None:
    header = _find_header(table)
    if header is None:
        return None
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


def _locator_accepts(table: PDFTable, locator: RegressionLocator | None) -> bool:
    if locator is None:
        return True
    if locator.expected_page is not None and table.page != locator.expected_page:
        return False
    requested_label = locator.canonical_table_label()
    if requested_label is not None and table.publication_label != requested_label:
        return False
    return True


def _match_numeric_signature(match: RegressionTableMatch) -> tuple[str | None, ...]:
    row = match.table.rows[match.data_row_index]
    signature: list[str | None] = []
    for key in ("beta", "se", "t_stat", "p_value"):
        index = match.columns.get(key)
        if index is None or index >= len(row) or row[index] is None:
            signature.append(None)
            continue
        raw = str(row[index])
        try:
            signature.append(_canonical_number(raw))
        except ValueError:
            signature.append(" ".join(raw.split()))
    return tuple(signature)


def _match_identity(match: RegressionTableMatch) -> tuple[object, ...]:
    publication_label = match.table.publication_label
    if publication_label is not None:
        return (match.table.page, publication_label, match.variable_text.casefold())
    # Unlabelled native continuations are intentionally not merged with geometry matches.
    return (
        match.table.page,
        _table_source_id(match.table),
        round(match.table.bbox[0], 1),
        round(match.table.bbox[1], 1),
        match.variable_text.casefold(),
    )


def _find_matches(
    snapshot: NativePDFSnapshot,
    variable_label: str,
    *,
    locator: RegressionLocator | None,
) -> tuple[RegressionTableMatch, ...]:
    target = " ".join(variable_label.casefold().split())
    matches: list[RegressionTableMatch] = []
    for table in snapshot.tables:
        if not _locator_accepts(table, locator):
            continue
        match = _match_table(snapshot, table, target=target)
        if match is not None:
            matches.append(match)

    requested_label = locator.table_label if locator is not None else None
    virtual_tables = reconstruct_borderless_tables(
        snapshot,
        variable_label=variable_label,
        role_resolver=_header_role,
        table_label=requested_label,
    )
    for table in virtual_tables:
        if not _locator_accepts(table, locator):
            continue
        match = _match_table(snapshot, table, target=target)
        if match is not None:
            matches.append(match)
    return tuple(matches)


def _resolve_match(
    snapshot: NativePDFSnapshot,
    variable_label: str,
    *,
    locator: RegressionLocator | None,
) -> tuple[RegressionTableMatch | None, str | None]:
    matches = _find_matches(snapshot, variable_label, locator=locator)
    if not matches:
        return None, None

    groups: dict[tuple[object, ...], list[RegressionTableMatch]] = {}
    for match in matches:
        groups.setdefault(_match_identity(match), []).append(match)

    resolved: list[RegressionTableMatch] = []
    for identity, group in groups.items():
        signatures = {_match_numeric_signature(match) for match in group}
        if len(signatures) > 1:
            return None, (
                f"{snapshot.parser_id}: conflicting extraction modes for display item {identity!r} "
                f"and variable {variable_label!r}"
            )
        # Prefer a parser's native table object over its geometry reconstruction only after
        # publication identity and numeric content agree.
        resolved.append(sorted(group, key=lambda match: match.table.table_index < 0)[0])

    if len(resolved) > 1:
        identities = tuple(_match_identity(match) for match in resolved)
        return None, (
            f"{snapshot.parser_id}: ambiguous display item for variable {variable_label!r}; "
            f"matched {identities!r}"
        )
    return resolved[0], None


def _candidate(match: RegressionTableMatch, key: str, raw: str, normalized: str) -> ExtractionCandidate:
    mode = _extraction_mode(match.table)
    base_score = 0.02 if mode == "word_geometry_v1" else 0.01
    header_penalty = 0.0 if key in match.columns else 0.02
    table_penalty = 0.0 if len(match.table.rows) >= 2 else 0.02
    return ExtractionCandidate(
        parser_id=f"{match.snapshot.parser_id}:{mode}",
        parser_family=match.snapshot.parser_family,
        raw=raw,
        normalized_value=normalized,
        nonconformity_score=base_score + header_penalty + table_penalty,
        source=match.source_for(raw),
    )


def extract_regression_table(
    snapshots: tuple[NativePDFSnapshot, ...],
    *,
    variable_label: str,
    locator: RegressionLocator | None = None,
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
    ambiguities: list[str] = []

    for snapshot in snapshots:
        match, ambiguity = _resolve_match(snapshot, variable_label, locator=locator)
        if ambiguity is not None:
            ambiguities.append(ambiguity)
            continue
        if match is None:
            continue
        row = match.table.rows[match.data_row_index]
        canonical_source = canonical_source or SourceLocation(
            artifact_id=snapshot.artifact_id,
            page=match.table.page,
            table=_source_table_label(match.table),
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
    parser_versions = [(snapshot.parser_id, snapshot.parser_version) for snapshot in snapshots]
    parser_versions.append(("veritas_regression_geometry", "1.1.0"))
    return RegressionExtractionBundle(
        artifact_id=next(iter(artifact_ids)),
        artifact_sha256=next(iter(artifact_hashes)),
        parser_versions=tuple(sorted(parser_versions)),
        field_candidates={key: tuple(value) for key, value in fields.items()},
        semantic_candidates={key: tuple(value) for key, value in semantics.items()},
        source=source,
        ambiguities=tuple(ambiguities),
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
        spec_version="regression-native-table-v4",
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
        object_schema_version="regression-native-table-v4",
        calibration_sha256=calibration_sha256,
        parser_versions=bundle.parser_versions,
        policy_note=(
            "PyMuPDF and pdfplumber independently provide word/table evidence. Publication table captions are preserved; "
            "a shared deterministic header-anchored geometry fallback is applied separately to each parser word stream. "
            "Ambiguous display-item identity is fail-closed, and hard promotion still requires cross-family value agreement "
            "plus explicit z-inference semantics."
        ),
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
            evidence_note=f"Dual native/geometry table extraction for {key}.",
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
    locator: RegressionLocator | None = None,
    artifact_id: str = "paper",
    object_id: str = "regression-1",
) -> tuple[EvidenceLedger, PromotionSpec]:
    snapshots = parse_pdf_dual(pdf_bytes, artifact_id=artifact_id)
    bundle = extract_regression_table(snapshots, variable_label=variable_label, locator=locator)
    ledger = bundle_to_ledger(
        bundle,
        gate,
        calibration_sha256=calibration_sha256,
        object_id=object_id,
    )
    return ledger, regression_promotion_spec()


def calibration_manifest_sha256(payload: bytes) -> str:
    return sha256(payload).hexdigest()
