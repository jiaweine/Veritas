from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .extraction_review import ExtractionAdjudication, ExtractionReviewSubmission
from .models import SourceLocation

_SUBMISSION_KEYS = frozenset(
    {"schema_version", "target_id", "reviewer_id", "accepted_normalized_values", "source", "note"}
)
_ADJUDICATION_KEYS = frozenset(
    {
        "schema_version",
        "target_id",
        "adjudicator_id",
        "accepted_normalized_values",
        "source",
        "note",
    }
)
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


def extraction_review_submission_json_payload(
    submission: ExtractionReviewSubmission,
) -> dict[str, object]:
    if not isinstance(submission, ExtractionReviewSubmission):
        raise TypeError("submission must be an ExtractionReviewSubmission")
    return {
        "schema_version": 1,
        "target_id": submission.target_id,
        "reviewer_id": submission.reviewer_id,
        "accepted_normalized_values": list(submission.accepted_normalized_values),
        "source": _source_payload(submission.source),
        "note": submission.note,
    }


def extraction_adjudication_json_payload(
    adjudication: ExtractionAdjudication,
) -> dict[str, object]:
    if not isinstance(adjudication, ExtractionAdjudication):
        raise TypeError("adjudication must be an ExtractionAdjudication")
    return {
        "schema_version": 1,
        "target_id": adjudication.target_id,
        "adjudicator_id": adjudication.adjudicator_id,
        "accepted_normalized_values": list(adjudication.accepted_normalized_values),
        "source": _source_payload(adjudication.source),
        "note": adjudication.note,
    }


def load_extraction_review_submission(path: str | Path) -> ExtractionReviewSubmission:
    payload = _load_strict_json_file(path, label="extraction review submission")
    _require_exact_keys(payload, _SUBMISSION_KEYS, label="extraction review submission")
    _require_schema_version(payload["schema_version"], label="extraction review submission")
    return ExtractionReviewSubmission(
        target_id=_nonempty_string(payload["target_id"], label="target_id"),
        reviewer_id=_nonempty_string(payload["reviewer_id"], label="reviewer_id"),
        accepted_normalized_values=_string_tuple(
            payload["accepted_normalized_values"], label="accepted_normalized_values"
        ),
        source=_source_from_mapping(payload["source"], label="review submission source"),
        note=_string(payload["note"], label="note"),
    )


def load_extraction_adjudication(path: str | Path) -> ExtractionAdjudication:
    payload = _load_strict_json_file(path, label="extraction adjudication")
    _require_exact_keys(payload, _ADJUDICATION_KEYS, label="extraction adjudication")
    _require_schema_version(payload["schema_version"], label="extraction adjudication")
    return ExtractionAdjudication(
        target_id=_nonempty_string(payload["target_id"], label="target_id"),
        adjudicator_id=_nonempty_string(payload["adjudicator_id"], label="adjudicator_id"),
        accepted_normalized_values=_string_tuple(
            payload["accepted_normalized_values"], label="accepted_normalized_values"
        ),
        source=_source_from_mapping(payload["source"], label="adjudication source"),
        note=_nonempty_string(payload["note"], label="note"),
    )


def _source_payload(source: SourceLocation) -> dict[str, object]:
    return {
        "artifact_id": source.artifact_id,
        "page": source.page,
        "section": source.section,
        "table": source.table,
        "figure": source.figure,
        "row": source.row,
        "column": source.column,
        "char_start": source.char_start,
        "char_end": source.char_end,
        "bbox": list(source.bbox) if source.bbox is not None else None,
        "text_quote": source.text_quote,
    }


def _source_from_mapping(value: object, *, label: str) -> SourceLocation:
    _require_exact_keys(value, _SOURCE_KEYS, label=label)
    bbox_payload = value["bbox"]
    bbox = None
    if bbox_payload is not None:
        if not isinstance(bbox_payload, list) or len(bbox_payload) != 4:
            raise TypeError(f"{label} bbox must be a four-number array or null")
        bbox = tuple(_finite_number(item, label=f"{label} bbox") for item in bbox_payload)
    page = _optional_int(value["page"], label=f"{label} page")
    if page is not None and page <= 0:
        raise ValueError(f"{label} page must be positive when present")
    char_start = _optional_int(value["char_start"], label=f"{label} char_start")
    char_end = _optional_int(value["char_end"], label=f"{label} char_end")
    if char_start is not None and char_start < 0:
        raise ValueError(f"{label} char_start must be non-negative")
    if char_end is not None and char_end < 0:
        raise ValueError(f"{label} char_end must be non-negative")
    if char_start is not None and char_end is not None and char_end < char_start:
        raise ValueError(f"{label} char_end must not precede char_start")
    return SourceLocation(
        artifact_id=_nonempty_string(value["artifact_id"], label=f"{label} artifact_id"),
        page=page,
        section=_optional_string(value["section"], label=f"{label} section"),
        table=_optional_string(value["table"], label=f"{label} table"),
        figure=_optional_string(value["figure"], label=f"{label} figure"),
        row=_optional_string(value["row"], label=f"{label} row"),
        column=_optional_string(value["column"], label=f"{label} column"),
        char_start=char_start,
        char_end=char_end,
        bbox=bbox,
        text_quote=_optional_string(value["text_quote"], label=f"{label} text_quote"),
    )


def _load_strict_json_file(path: str | Path, *, label: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc

    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate JSON object key: {key!r}")
            result[key] = item
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"{label} contains unsupported JSON numeric constant: {value}")

    try:
        payload = json.loads(
            text,
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{label} must be a JSON object")
    return payload


def _require_exact_keys(value: object, expected: frozenset[str], *, label: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object")
    actual = set(value)
    if actual != expected:
        missing = tuple(sorted(expected - actual))
        extra = tuple(sorted(actual - expected))
        raise ValueError(f"{label} keys differ from schema; missing={missing!r}, extra={extra!r}")


def _require_schema_version(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} schema_version must be integer 1")
    if value != 1:
        raise ValueError(f"{label} schema_version must be integer 1")


def _string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty array")
    result = tuple(_nonempty_string(item, label=label) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{label} values must be unique")
    return result


def _nonempty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _string(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _optional_string(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string or null")
    return value


def _optional_int(value: object, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer or null")
    return value


def _finite_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result
