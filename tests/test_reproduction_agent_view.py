from __future__ import annotations

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    MethodField,
    MethodSpecification,
    ReproductionArtifact,
    ReproductionMode,
    ReproductionTarget,
    build_code_agent_task,
)
from veritas.reproduction_agent_view import build_agent_task_view


def test_agent_view_strips_method_source_quotes_that_may_contain_result_values() -> None:
    task = build_code_agent_task(
        task_id="blind",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=MethodSpecification(
            spec_id="method",
            object_type="RegressionResult",
            fields=(
                MethodField(
                    "estimator",
                    "ols",
                    source=SourceLocation(
                        page=4,
                        section="Methods",
                        text_quote="We estimated OLS; the focal coefficient was 9.87654321.",
                        char_start=100,
                        char_end=160,
                        bbox=(10.0, 20.0, 30.0, 40.0),
                    ),
                ),
            ),
        ),
        artifacts=(ReproductionArtifact("data", "analysis_data", "a" * 64, "file:///data.csv"),),
        targets=(
            ReproductionTarget(
                "beta",
                "claim",
                "coefficient",
                ReportedNumber(9.87654321, decimals=8),
                SourceLocation(page=5, table="Table 2", row="Treatment", column="B"),
            ),
        ),
    )

    view = build_agent_task_view(task)
    rendered = view.to_json()
    assert "9.87654321" not in rendered
    assert "text_quote" not in rendered
    assert "char_start" not in rendered
    assert "bbox" not in rendered
    assert view.method_fields[0].source.page == 4
    assert view.method_fields[0].source.section == "Methods"


def test_agent_view_contains_output_identity_but_not_reported_number() -> None:
    task = build_code_agent_task(
        task_id="blind-target",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=MethodSpecification(
            spec_id="method",
            object_type="RegressionResult",
            fields=(MethodField("estimator", "ols"),),
        ),
        artifacts=(ReproductionArtifact("data", "analysis_data", "a" * 64),),
        targets=(
            ReproductionTarget(
                "table2-treatment-p",
                "claim-main",
                "p_value",
                ReportedNumber(0.000123, decimals=6),
                SourceLocation(page=5, table="Table 2", row="Treatment", column="p"),
            ),
        ),
    )

    view = build_agent_task_view(task)
    rendered = view.to_json()
    assert "table2-treatment-p" in rendered
    assert "claim-main" in rendered
    assert "p_value" in rendered
    assert "0.000123" not in rendered
