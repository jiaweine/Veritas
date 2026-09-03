from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import ReportedNumber, SourceLocation
from .reproduction import ReproductionTarget
from .reproduction_json import finite_reproduction_float
from .types import ComparisonOperator, Materiality

_TARGET_REQUIRED = frozenset({"target_id", "claim_id", "metric", "reported"})
_TARGET_OPTIONAL = frozenset({"source", "materiality"})
_REPORTED_REQUIRED = frozenset({"value"})
_REPORTED_OPTIONAL = frozenset({"decimals", "operator"})
_SOURCE_KEYS = frozenset(
    {
        "artifact_id",
        "page",
        "section",
        "table",
        "figure",
        "row",
        "column",
        "char_start",
        "char_end",
        "bbox",
        "text_quote",
    }
)
_SOURCE_TEXT_KEYS = frozenset(
    {"artifact_id", "section", "table", "figure", "row", "column", "text_quote"}
)
_SOURCE_INT_KEYS = frozenset({"page", "char_start", "char_end"})


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _require_exact_keys(
    mapping: Mapping[str, Any],
    *,
    label: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    observed = set(mapping)
    missing = sorted(required - observed)
    if missing:
        raise ValueError(f"{label} is missing required fields: {missing!r}")
    unexpected = sorted(observed - required - optional)
    if unexpected:
        raise ValueError(f"{label} contains unexpected fields: {unexpected!r}")


def _require_nonempty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{label} must be a non-empty string")
    return value


def _require_optional_string(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string or null")
    return value


def _require_int(value: object, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return value


def _require_json_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a JSON number")
    return finite_reproduction_float(value, label=label)


def _parse_reported(value: object) -> ReportedNumber:
    reported = _require_mapping(value, label="private target reported")
    _require_exact_keys(
        reported,
        label="private target reported",
        required=_REPORTED_REQUIRED,
        optional=_REPORTED_OPTIONAL,
    )
    decimals_value = reported.get("decimals")
    decimals = None
    if decimals_value is not None:
        decimals = _require_int(
            decimals_value,
            label="private target reported decimals",
            minimum=0,
        )
    operator_value = reported.get("operator", "=")
    if not isinstance(operator_value, str):
        raise TypeError("private target reported operator must be a string")
    try:
        operator = ComparisonOperator(operator_value)
    except ValueError as exc:
        raise ValueError("private target reported operator is unsupported") from exc
    return ReportedNumber(
        value=_require_json_number(
            reported["value"],
            label="private target reported value",
        ),
        decimals=decimals,
        operator=operator,
    )


def _parse_source(value: object) -> SourceLocation:
    source = _require_mapping(value, label="private target source")
    unexpected = sorted(set(source) - _SOURCE_KEYS)
    if unexpected:
        raise ValueError(f"private target source contains unexpected fields: {unexpected!r}")

    normalized: dict[str, Any] = {}
    for key in _SOURCE_TEXT_KEYS:
        if key not in source:
            continue
        normalized[key] = _require_optional_string(
            source[key],
            label=f"private target source {key}",
        )
    if "artifact_id" in normalized and not normalized["artifact_id"]:
        raise ValueError("private target source artifact_id must not be empty")

    for key in _SOURCE_INT_KEYS:
        if key not in source or source[key] is None:
            continue
        minimum = 1 if key == "page" else 0
        normalized[key] = _require_int(
            source[key],
            label=f"private target source {key}",
            minimum=minimum,
        )

    if "char_start" in normalized and "char_end" in normalized:
        if normalized["char_end"] < normalized["char_start"]:
            raise ValueError("private target source char_end must be >= char_start")

    if "bbox" in source and source["bbox"] is not None:
        bbox = source["bbox"]
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise TypeError("private target source bbox must be a four-number JSON array")
        normalized["bbox"] = tuple(
            _require_json_number(component, label="private target source bbox component")
            for component in bbox
        )

    return SourceLocation(**normalized)


def reproduction_target_from_secret_mapping(
    value: object,
    *,
    allow_schema_version: bool,
) -> ReproductionTarget:
    """Construct one sealed target only after an exact, typed secret-schema check."""

    target = _require_mapping(value, label="private target")
    optional = _TARGET_OPTIONAL | (frozenset({"schema_version"}) if allow_schema_version else frozenset())
    _require_exact_keys(
        target,
        label="private target",
        required=_TARGET_REQUIRED,
        optional=optional,
    )
    if "schema_version" in target:
        schema_version = _require_int(target["schema_version"], label="private target schema_version")
        if schema_version != 1:
            raise ValueError("unsupported private target schema_version")

    materiality_value = target.get("materiality", int(Materiality.SECONDARY_RESULT))
    materiality_int = _require_int(
        materiality_value,
        label="private target materiality",
        minimum=int(Materiality.FORMATTING),
    )
    try:
        materiality = Materiality(materiality_int)
    except ValueError as exc:
        raise ValueError("private target materiality is unsupported") from exc

    source_value = target.get("source", {})
    return ReproductionTarget(
        target_id=_require_nonempty_string(target["target_id"], label="private target target_id"),
        claim_id=_require_nonempty_string(target["claim_id"], label="private target claim_id"),
        metric=_require_nonempty_string(target["metric"], label="private target metric"),
        reported=_parse_reported(target["reported"]),
        source=_parse_source(source_value),
        materiality=materiality,
    )
