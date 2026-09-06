from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .extraction_execution_evidence import ExtractionExecutionPlan


def extraction_execution_artifact_sha256(path: str | Path) -> str:
    """Return the SHA-256 of the exact archived artifact bytes."""
    return sha256(Path(path).read_bytes()).hexdigest()


def build_extraction_execution_plan_from_artifacts(
    *,
    input_artifact_manifest: str | Path,
    source_tree: str | Path,
    parser_registry: str | Path,
    numerical_runtime: str | Path,
    execution_command: str | Path,
) -> ExtractionExecutionPlan:
    """Build the safe execution plan from exact archived artifact bytes."""
    return ExtractionExecutionPlan(
        input_artifact_manifest_sha256=extraction_execution_artifact_sha256(
            input_artifact_manifest
        ),
        source_tree_sha256=extraction_execution_artifact_sha256(source_tree),
        parser_registry_sha256=extraction_execution_artifact_sha256(parser_registry),
        numerical_runtime_sha256=extraction_execution_artifact_sha256(numerical_runtime),
        execution_command_sha256=extraction_execution_artifact_sha256(execution_command),
    )


def verify_extraction_execution_plan_artifacts(
    plan: ExtractionExecutionPlan,
    *,
    input_artifact_manifest: str | Path,
    source_tree: str | Path,
    parser_registry: str | Path,
    numerical_runtime: str | Path,
    execution_command: str | Path,
) -> None:
    """Require every execution-plan digest to match its exact archived artifact bytes."""
    if not isinstance(plan, ExtractionExecutionPlan):
        raise TypeError("plan must be an ExtractionExecutionPlan")
    actual = {
        "input_artifact_manifest_sha256": extraction_execution_artifact_sha256(
            input_artifact_manifest
        ),
        "source_tree_sha256": extraction_execution_artifact_sha256(source_tree),
        "parser_registry_sha256": extraction_execution_artifact_sha256(parser_registry),
        "numerical_runtime_sha256": extraction_execution_artifact_sha256(numerical_runtime),
        "execution_command_sha256": extraction_execution_artifact_sha256(execution_command),
    }
    for field, digest in actual.items():
        if getattr(plan, field) != digest:
            label = field.removesuffix("_sha256").replace("_", " ")
            raise ValueError(f"execution plan {label} differs from archived artifact bytes")
