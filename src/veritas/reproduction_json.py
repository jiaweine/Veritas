from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError(f"reproduction JSON contains duplicate object key: {key!r}")
        decoded[key] = value
    return decoded


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"reproduction JSON contains unsupported numeric constant: {value}")


def loads_strict_reproduction_json(text: str) -> Any:
    """Decode RFC-style JSON while rejecting ambiguous or non-finite extensions."""

    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("reproduction input must be valid JSON") from exc


def load_strict_reproduction_json(path: str | Path) -> Any:
    """Read a UTF-8 reproduction control/output file through the strict decoder."""

    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("reproduction input must be valid UTF-8 JSON") from exc
    return loads_strict_reproduction_json(text)


def finite_reproduction_float(value: object, *, label: str) -> float:
    """Convert a numeric control value without permitting booleans or non-finite floats."""

    if isinstance(value, bool):
        raise TypeError(f"{label} must be numeric")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric
