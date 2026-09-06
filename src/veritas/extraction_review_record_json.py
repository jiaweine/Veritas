from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .extraction_review import (
    ExtractionAdjudication,
    ExtractionReviewRecord,
    ExtractionReviewSubmission,
    ExtractionReviewTarget,
)
from .ingestion import EvidenceKind
from .models import SourceLocation

_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "target",
        "submissions",
        "accepted_normalized_values",
        "source",
        "adjudication",
    }
)
_TARGET_KEYS = frozenset(
    {
        "target_id",
        "paper_id",
        "article_family_id",
        "object_type",
        "key",
        "kind",
        "critical_for_hard_audit",
    }
)
_SUBMISSION_KEYS = frozenset(
    {"target_id", "reviewer_id", "accepted_normalized_values", "source", "note"}
)
_ADJUDICATION_KEYS = frozenset(
    {
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


def extraction_review_record_json_payload(record: ExtractionReviewRecord) -> dict[str, object]:
    if not isinstance(record, ExtractionReviewRecord):
        raise TypeError("record must be an ExtractionReviewRecord")
    return {
        "schema_version": record.schema_version,
        "target": {
            "target_id": record.target.target_id,
            "paper_id": record.target.paper_id,
            "article_family_id": record.target.article_family_id,
            "object_type": record.target.object_type,
            "key": record.target.key,
            "kind": record.target.kind.value,
            "critical_for_hard_audit": record.target.critical_for_hard_audit,
        },
        "submissions": [
            {
                "target_id": submission.target_id,
                "reviewer_id": submission.reviewer_id,
                "accepted_normalized_values": list(submission.accepted_normalized_values),
                "source": _source_payload(submission.source),
                "note": submission.note,
            }
            for submission in sorted(record.submissions, key=lambda item: item.reviewer_id)
        ],
        "accepted_normalized_values": list(record.accepted_normalized_values),
        "source": _source_payload(record.source),
        "adjudication": (
            {
                "target_id": record.adjudication.target_id,
                "adjudicator_id": record.adjudication.adjudicator_id,
                "accepted_normalized_values": list(
                    record.adjudication.accepted_normalized_values
                ),
                "source": _source_payload(record.adjudication.source),
                "note": record.adjudication.note,
            }
            if record.adjudication is not None
            else None
        ),
    }


def load_extraction_review_record(path: str | Path) -> ExtractionReviewRecord:
    payload = _load_strict_json_file(path, label="extraction review record")
    return extraction_review_record_from_mapping(payload, label="extraction review record")


def extraction_review_record_from_mapping(
    value: object,
    *,
    label: str = "extraction review record",
) -> ExtractionReviewRecord:
    _require_exact_keys(value, _RECORD_KEYS, label=label)
    target_payload = value["target"]
    _require_exact_keys(target_payload, _TARGET_KEYS, label=f"{label} target")
    kind_value = target_payload["kind"]
    if not isinstance(kind_value, str):
        raise TypeError(f"{label} target kind must be a string")
    try:
        kind = EvidenceKind(kind_value)
    except ValueError as exc:
        raise ValueError(f"{label} target kind is unsupported") from exc
    critical = target_payload["critical_for_hard_audit"]
    if type(critical) is not bool:
        raise TypeError(f"{label} target critical_for_hard_audit must be boolean")
    target = ExtractionReviewTarget(
        target_id=_nonempty_string(target_payload["target_id"], label=f"{label} target_id"),
        paper_id=_nonempty_string(target_payload["paper_id"], label=f"{label} paper_id"),
        article_family_id=_nonempty_string(
            target_payload["article_family_id"], label=f"{label} article_family_id"
        ),
        object_type=_nonempty_string(
            target_payload["object_type"], label=f"{label} object_type"
        ),
        key=_nonempty_string(target_payload["key"], label=f"{label} key"),
        kind=kind,
        critical_for_hard_audit=critical,
    )

    submissions_payload = value["submissions"]
    if not isinstance(submissions_payload, list):
        raise TypeError(f"{label} submissions must be an array")
    submissions: list[ExtractionReviewSubmission] = []
    for index, submission_payload in enumerate(submissions_payload):
        submission_label = f"{label} submission {index}"
        _require_exact_keys(submission_payload, _SUBMISSION_KEYS, label=submission_label)
        submissions.append(
            ExtractionReviewSubmission(
                target_id=_nonempty_string(
                    submission_payload["target_id"], label=f"{submission_label} target_id"
                ),
                reviewer_id=_nonempty_string(
                    submission_payload["reviewer_id"], label=f"{submission_label} reviewer_id"
                ),
                accepted_normalized_values=_string_tuple(
                    submission_payload["accepted_normalized_values"],
                    label=f"{submission_label} accepted_normalized_values",
                ),
                source=_source_from_mapping(
                    submission_payload["source"], label=f"{submission_label} source"
                ),
                note=_string(submission_payload["note"], label=f"{submission_label} note"),
            )
        )

    adjudication_payload = value["adjudication"]
    adjudication = None
    if adjudication_payload is not None:
        _require_exact_keys(
            adjudication_payload,
            _ADJUDICATION_KEYS,
            label=f"{label} adjudication",
        )
        adjudication = ExtractionAdjudication(
            target_id=_nonempty_string(
                adjudication_payload["target_id"], label=f"{label} adjudication target_id"
            ),
            adjudicator_id=_nonempty_string(
                adjudication_payload["adjudicator_id"],
                label=f"{label} adjudication adjudicator_id",
            ),
            accepted_normalized_values=_string_tuple(
                adjudication_payload["accepted_normalized_values"],
                label=f"{label} adjudication accepted_normalized_values",
            ),
            source=_source_from_mapping(
                adjudication_payload["source"], label=f"{label} adjudication source"
            ),
            note=_nonempty_string(
                adjudication_payload["note"], label=f"{label} adjudication note"
            ),
        )

    schema_version = value["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise TypeError(f"{label} schema_version must be integer 1")
    if schema_version != 1:
        raise ValueError(f"{label} schema_version must be integer 1")

    return ExtractionReviewRecord(
        target=target,
        submissions=tuple(submissions),
        accepted_normalized_values=_string_tuple(
            value["accepted_normalized_values"],
            label=f"{label} accepted_normalized_values",
        ),
        source=_source_from_mapping(value["source"], label=f"{label} source"),
        adjudication=adjudication,
        schema_version=schema_version,
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
    return SourceLocation(
        artifact_id=_nonempty_string(value["artifact_id"], label=f"{label} artifact_id"),
        page=_optional_int(value["page"], label=f"{label} page"),
        section=_optional_string(value["section"], label=f"{label} section"),
        table=_optional_string(value["table"], label=f"{label} table"),
        figure=_optional_string(value["figure"], label=f"{label} figure"),
        row=_optional_string(value["row"], label=f"{label} row"),
        column=_optional_string(value["column"], label=f"{label} column"),
        char_start=_optional_int(value["char_start"], label=f"{label} char_start"),
        char_end=_optional_int(value["char_end"], label=f"{label} char_end"),
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
