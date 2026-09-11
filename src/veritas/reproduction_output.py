from __future__ import annotations

from hashlib import sha256
from math import isfinite

from .reproduction import CodeAgentTask, ReproducedCell
from .reproduction_json import loads_strict_reproduction_json


class ReproductionOutputError(ValueError):
    pass


def _decode_reproduction_output(payload: bytes):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReproductionOutputError("reproduction output must be valid UTF-8 JSON") from exc

    try:
        return loads_strict_reproduction_json(text)
    except ValueError as exc:
        message = str(exc)
        if "duplicate object key" in message:
            raise ReproductionOutputError("reproduction output contains duplicate object keys") from exc
        if "unsupported numeric constant" in message:
            raise ReproductionOutputError(
                "reproduction output contains unsupported non-finite numeric value"
            ) from exc
        raise ReproductionOutputError("reproduction output must be valid UTF-8 JSON") from exc


def parse_reproduction_output(payload: bytes, task: CodeAgentTask) -> tuple[ReproducedCell, ...]:
    """Parse the only machine-readable result format accepted from a reproduction workspace.

    The output artifact is hashed from the exact bytes supplied by the independent executor. Extra
    keys are rejected so an agent cannot smuggle comparison claims or target values into the result
    record and have them mistaken for verifier evidence.
    """

    artifact_sha256 = sha256(payload).hexdigest()
    decoded = _decode_reproduction_output(payload)

    if not isinstance(decoded, dict) or set(decoded) != {"schema_version", "targets"}:
        raise ReproductionOutputError("output must contain exactly schema_version and targets")
    if isinstance(decoded["schema_version"], bool) or decoded["schema_version"] != 1:
        raise ReproductionOutputError("unsupported reproduction output schema_version")
    if not isinstance(decoded["targets"], list):
        raise ReproductionOutputError("targets must be a JSON array")

    allowed = set(task.target_ids)
    seen: set[str] = set()
    cells: list[ReproducedCell] = []
    for row in decoded["targets"]:
        if not isinstance(row, dict) or set(row) != {"target_id", "value"}:
            raise ReproductionOutputError("each target row must contain exactly target_id and value")
        target_id = row["target_id"]
        value = row["value"]
        if not isinstance(target_id, str) or target_id not in allowed:
            raise ReproductionOutputError(f"unexpected target_id: {target_id!r}")
        if target_id in seen:
            raise ReproductionOutputError(f"duplicate target_id: {target_id!r}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise ReproductionOutputError(f"target {target_id!r} must contain one finite numeric value")
        seen.add(target_id)
        cells.append(
            ReproducedCell(
                target_id=target_id,
                value=float(value),
                output_artifact_sha256=artifact_sha256,
            )
        )
    return tuple(cells)


def reproduction_output_instructions(task: CodeAgentTask) -> str:
    """Stable output instructions that can be appended to any coding-agent scaffold."""

    target_lines = "\n".join(f"- {item.target_id}: {item.metric}" for item in task.targets)
    return (
        "Write the final computational outputs to reproduction_results.json.\n"
        "The file MUST be UTF-8 JSON with exactly this shape:\n"
        '{"schema_version":1,"targets":[{"target_id":"...","value":0.0}]}\n'
        "Emit only targets that you actually computed; do not guess missing outputs.\n"
        "Do not include reported paper values, comparison judgments, explanations, or extra keys.\n"
        "Required output identities:\n"
        f"{target_lines}\n"
    )
