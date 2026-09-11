from __future__ import annotations

import pytest

from veritas.models import ReportedNumber, SourceLocation
from veritas.reproduction import (
    AgentVisibilityPolicy,
    CodeAgentTask,
    MethodField,
    MethodSpecification,
    ReproductionArtifact,
    ReproductionMode,
    ReproductionTarget,
    build_code_agent_task,
)
from veritas.reproduction_agent_view import AgentTaskViewBlocked, build_agent_task_view


def test_agent_view_strips_method_provenance_that_may_fingerprint_or_leak_results() -> None:
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
                        table="Table 9",
                        row="Distinctive treatment label",
                        column="Estimate",
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
    assert "Table 9" not in rendered
    assert "Distinctive treatment label" not in rendered
    assert "Methods" not in rendered
    assert "file:///data.csv" not in rendered
    assert "uri" not in rendered
    assert view.method_fields[0].name == "estimator"
    assert view.method_fields[0].value == "ols"


def test_agent_view_contains_output_identity_but_not_internal_paper_identity() -> None:
    task = build_code_agent_task(
        task_id="ssrn-7138278-internal-task",
        mode=ReproductionMode.INDEPENDENT_REIMPLEMENTATION,
        method_spec=MethodSpecification(
            spec_id="doi:10.1234/internal-method",
            object_type="RegressionResult",
            fields=(MethodField("estimator", "ols"),),
        ),
        artifacts=(ReproductionArtifact("data", "analysis_data", "a" * 64),),
        targets=(
            ReproductionTarget(
                "target-1",
                "doi:10.1234/internal-claim",
                "p_value",
                ReportedNumber(0.000123, decimals=6),
                SourceLocation(page=5, table="Table 2", row="Treatment", column="p"),
            ),
        ),
    )

    view = build_agent_task_view(task)
    rendered = view.to_json()
    assert "target-1" in rendered
    assert "p_value" in rendered
    assert "0.000123" not in rendered
    assert "ssrn-7138278-internal-task" not in rendered
    assert "doi:10.1234/internal-method" not in rendered
    assert "doi:10.1234/internal-claim" not in rendered
    assert not hasattr(view, "task_id")
    assert not hasattr(view, "method_spec_id")
    assert not hasattr(view.targets[0], "claim_id")


def test_independent_agent_view_rejects_paper_or_result_artifacts_even_for_manual_tasks() -> None:
    safe_task = build_code_agent_task(
        task_id="blind-artifacts",
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
                "claim",
                "coefficient",
                ReportedNumber(0.4, decimals=1),
                SourceLocation(page=2, table="Table 1"),
            ),
        ),
    )
    unsafe_task = CodeAgentTask(
        task_id=safe_task.task_id,
        mode=safe_task.mode,
        method_spec=safe_task.method_spec,
        artifacts=safe_task.artifacts
        + (ReproductionArtifact("paper", "paper", "b" * 64, "https://example.test/paper.pdf"),),
        targets=safe_task.targets,
        reference_commitment_sha256=safe_task.reference_commitment_sha256,
        visibility_policy=safe_task.visibility_policy,
    )

    with pytest.raises(AgentTaskViewBlocked, match="disallowed roles"):
        build_agent_task_view(unsafe_task)


def test_independent_agent_view_rechecks_visibility_policy_for_manual_tasks() -> None:
    safe_task = build_code_agent_task(
        task_id="blind-policy",
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
                "claim",
                "coefficient",
                ReportedNumber(0.4, decimals=1),
                SourceLocation(page=2, table="Table 1"),
            ),
        ),
    )
    unsafe_task = CodeAgentTask(
        task_id=safe_task.task_id,
        mode=safe_task.mode,
        method_spec=safe_task.method_spec,
        artifacts=safe_task.artifacts,
        targets=safe_task.targets,
        reference_commitment_sha256=safe_task.reference_commitment_sha256,
        visibility_policy=AgentVisibilityPolicy(allow_reported_outcomes=True),
    )

    with pytest.raises(AgentTaskViewBlocked, match="reported outcomes"):
        build_agent_task_view(unsafe_task)


def test_independent_agent_view_rejects_network_even_without_explicit_target_values() -> None:
    safe_task = build_code_agent_task(
        task_id="blind-network",
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
                "claim",
                "coefficient",
                ReportedNumber(0.4, decimals=1),
                SourceLocation(page=2, table="Table 1"),
            ),
        ),
    )
    networked_task = CodeAgentTask(
        task_id=safe_task.task_id,
        mode=safe_task.mode,
        method_spec=safe_task.method_spec,
        artifacts=safe_task.artifacts,
        targets=safe_task.targets,
        reference_commitment_sha256=safe_task.reference_commitment_sha256,
        visibility_policy=AgentVisibilityPolicy(allow_network=True),
    )

    with pytest.raises(AgentTaskViewBlocked, match="disable agent network access"):
        build_agent_task_view(networked_task)
