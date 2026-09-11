from __future__ import annotations

import json

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    MethodField,
    MethodSpecification,
    ReproductionArtifact,
    ReproductionMode,
    ReproductionTarget,
    build_code_agent_task,
)
from veritas.reproduction_output import (
    ReproductionOutputError,
    parse_reproduction_output,
    reproduction_output_instructions,
)


def _task():
    return build_code_agent_task(
        task_id="output",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=MethodSpecification(
            spec_id="method",
            object_type="RegressionResult",
            fields=(MethodField("estimator", "ols"),),
        ),
        artifacts=(ReproductionArtifact("data", "analysis_data", "a" * 64),),
        targets=(
            ReproductionTarget(
                "beta",
                "claim-main",
                "coefficient",
                ReportedNumber(0.1, decimals=2),
                SourceLocation(page=1, table="Table 1", row="x", column="B"),
            ),
            ReproductionTarget(
                "se",
                "claim-main",
                "standard_error",
                ReportedNumber(0.02, decimals=2),
                SourceLocation(page=1, table="Table 1", row="x", column="SE"),
            ),
        ),
    )


def test_output_parser_binds_cells_to_exact_output_artifact_hash() -> None:
    task = _task()
    payload = json.dumps(
        {"schema_version": 1, "targets": [{"target_id": "beta", "value": 0.101}]},
        separators=(",", ":"),
    ).encode()
    cells = parse_reproduction_output(payload, task)

    assert len(cells) == 1
    assert cells[0].target_id == "beta"
    assert cells[0].value == pytest.approx(0.101)
    assert len(cells[0].output_artifact_sha256) == 64


def test_output_parser_rejects_unrequested_targets_duplicates_and_extra_claims() -> None:
    task = _task()
    bad_payloads = (
        b'{"schema_version":1,"targets":[{"target_id":"p_value","value":0.01}]}',
        b'{"schema_version":1,"targets":[{"target_id":"beta","value":0.1},{"target_id":"beta","value":0.1}]}',
        b'{"schema_version":1,"targets":[{"target_id":"beta","value":0.1,"matches_paper":true}]}',
        b'{"schema_version":1,"targets":[],"paper_is_wrong":true}',
    )
    for payload in bad_payloads:
        with pytest.raises(ReproductionOutputError):
            parse_reproduction_output(payload, task)


def test_output_parser_rejects_duplicate_object_keys_before_schema_interpretation() -> None:
    task = _task()
    bad_payloads = (
        b'{"schema_version":1,"schema_version":1,"targets":[]}',
        b'{"schema_version":1,"targets":[{"target_id":"beta","value":0.1,"value":0.2}]}',
    )
    for payload in bad_payloads:
        with pytest.raises(ReproductionOutputError, match="duplicate object keys"):
            parse_reproduction_output(payload, task)


def test_output_parser_rejects_boolean_schema_version() -> None:
    with pytest.raises(ReproductionOutputError, match="schema_version"):
        parse_reproduction_output(b'{"schema_version":true,"targets":[]}', _task())


def test_output_parser_rejects_nan_boolean_and_non_numeric_values() -> None:
    task = _task()
    for value in (True, "0.1", None):
        payload = json.dumps(
            {"schema_version": 1, "targets": [{"target_id": "beta", "value": value}]}
        ).encode()
        with pytest.raises(ReproductionOutputError, match="finite numeric value"):
            parse_reproduction_output(payload, task)

    for constant in (b"NaN", b"Infinity", b"-Infinity"):
        payload = (
            b'{"schema_version":1,"targets":[{"target_id":"beta","value":'
            + constant
            + b"}]}"
        )
        with pytest.raises(ReproductionOutputError, match="finite numeric value"):
            parse_reproduction_output(payload, task)


def test_agent_output_instructions_expose_metrics_but_not_reported_values() -> None:
    task = _task()
    instructions = reproduction_output_instructions(task)
    assert "beta: coefficient" in instructions
    assert "se: standard_error" in instructions
    assert "0.1" not in instructions
    assert "0.02" not in instructions
