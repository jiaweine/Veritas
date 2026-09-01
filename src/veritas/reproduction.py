from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Protocol

from .models import ReportedNumber, SourceLocation
from .types import ComparisonOperator, EvidenceGrade, Materiality

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _stable_sha256(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return sha256(raw).hexdigest()


def _validate_sha256(name: str, value: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")


class ReproductionMode(str, Enum):
    AUTHOR_CODE = "author_code"
    INDEPENDENT_REIMPLEMENTATION = "independent_reimplementation"


class ReproductionAuthority(str, Enum):
    EXPERIMENTAL_AGENT = "experimental_agent"
    AUTHOR_PACKAGE_RERUN = "author_package_rerun"
    INDEPENDENT_ADJUDICATED = "independent_adjudicated"


class ReproductionDecision(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    PARTIAL = "partial"
    UNVERIFIABLE = "unverifiable"


class CellComparisonStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    MISSING = "missing"


class ReproductionRootCause(str, Enum):
    METHOD_UNDERSPECIFICATION = "method_underspecification"
    DATA_PREPROCESSING = "data_preprocessing"
    SAMPLE_SELECTION = "sample_selection"
    VARIABLE_CONSTRUCTION = "variable_construction"
    ESTIMATOR = "estimator"
    INFERENCE = "inference"
    RANDOMNESS = "randomness"
    ENVIRONMENT = "environment"
    AGENT_IMPLEMENTATION = "agent_implementation"
    UNKNOWN = "unknown"


class ReproductionBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class MethodField:
    name: str
    value: str | int | float | bool | None
    source: SourceLocation = field(default_factory=SourceLocation)
    confidence: float = 1.0
    required_for_execution: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("method field name is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("method field confidence must be in [0, 1]")


@dataclass(frozen=True)
class MethodSpecification:
    """Publication-grounded method contract supplied to an independent code agent."""

    spec_id: str
    object_type: str
    fields: tuple[MethodField, ...]
    version: str = "1"

    def __post_init__(self) -> None:
        if not self.spec_id.strip() or not self.object_type.strip():
            raise ValueError("spec_id and object_type are required")
        names = [item.name for item in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("method field names must be unique")

    def field_map(self) -> dict[str, MethodField]:
        return {item.name: item for item in self.fields}

    def missing_required_fields(self, *, min_confidence: float = 0.95) -> tuple[str, ...]:
        return tuple(
            item.name
            for item in self.fields
            if item.required_for_execution and (item.value is None or item.confidence < min_confidence)
        )

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class ReproductionArtifact:
    artifact_id: str
    role: str
    sha256: str
    uri: str | None = None

    def __post_init__(self) -> None:
        if not self.artifact_id.strip() or not self.role.strip():
            raise ValueError("artifact_id and role are required")
        _validate_sha256("artifact sha256", self.sha256)


@dataclass(frozen=True)
class ReproductionTarget:
    target_id: str
    claim_id: str
    metric: str
    reported: ReportedNumber
    source: SourceLocation
    materiality: Materiality = Materiality.SECONDARY_RESULT

    def reference_commitment_sha256(self) -> str:
        return _stable_sha256(
            {
                "target_id": self.target_id,
                "claim_id": self.claim_id,
                "metric": self.metric,
                "reported": {
                    "value": self.reported.value,
                    "decimals": self.reported.decimals,
                    "operator": self.reported.operator.value,
                },
                "source": asdict(self.source),
                "materiality": int(self.materiality),
            }
        )

    def blind_descriptor(self) -> AgentTargetDescriptor:
        return AgentTargetDescriptor(
            target_id=self.target_id,
            claim_id=self.claim_id,
            metric=self.metric,
        )


@dataclass(frozen=True)
class AgentTargetDescriptor:
    """What the agent must produce, without exposing the paper's numeric answer."""

    target_id: str
    claim_id: str
    metric: str


@dataclass(frozen=True)
class AgentVisibilityPolicy:
    allow_reported_outcomes: bool = False
    allow_original_code: bool = False
    allow_network: bool = False
    allow_package_install: bool = False
    reveal_numeric_comparison_during_iteration: bool = False

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class CodeAgentTask:
    task_id: str
    mode: ReproductionMode
    method_spec: MethodSpecification
    artifacts: tuple[ReproductionArtifact, ...]
    targets: tuple[AgentTargetDescriptor, ...]
    reference_commitment_sha256: str
    visibility_policy: AgentVisibilityPolicy

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.targets:
            raise ValueError("task_id and at least one target descriptor are required")
        _validate_sha256("reference commitment", self.reference_commitment_sha256)

    @property
    def target_ids(self) -> tuple[str, ...]:
        return tuple(item.target_id for item in self.targets)

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class CodeAgentProposal:
    """Code produced by an agent. It is not an execution or method-fidelity attestation."""

    agent_id: str
    agent_version: str
    task_sha256: str
    method_spec_sha256: str
    visibility_policy_sha256: str
    generated_code_sha256: str
    attempts: int
    original_code_patch_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.agent_id.strip() or not self.agent_version.strip():
            raise ValueError("agent identity is required")
        if self.attempts < 1:
            raise ValueError("attempts must be positive")
        for name, value in (
            ("task_sha256", self.task_sha256),
            ("method_spec_sha256", self.method_spec_sha256),
            ("visibility_policy_sha256", self.visibility_policy_sha256),
            ("generated_code_sha256", self.generated_code_sha256),
        ):
            _validate_sha256(name, value)
        if self.original_code_patch_sha256 is not None:
            _validate_sha256("original_code_patch_sha256", self.original_code_patch_sha256)


class AuthorCodeAgentBackend(Protocol):
    """Full-task adapter boundary reserved for author-code reproduction.

    Independent reimplementation backends must consume the leak-safe ``AgentTaskView`` through
    ``BlindCodeAgentBackend`` and ``dispatch_blind_code_agent`` instead of receiving a
    ``CodeAgentTask`` directly.
    """

    agent_id: str
    agent_version: str

    def solve(self, task: CodeAgentTask) -> CodeAgentProposal: ...


@dataclass(frozen=True)
class SandboxPolicy:
    network_disabled: bool = True
    read_only_inputs: bool = True
    max_wall_seconds: int = 3600
    max_memory_mb: int = 8192
    max_cpus: int = 4

    def __post_init__(self) -> None:
        if self.max_wall_seconds <= 0 or self.max_memory_mb <= 0 or self.max_cpus <= 0:
            raise ValueError("sandbox resource limits must be positive")

    def sha256(self) -> str:
        return _stable_sha256(asdict(self))


@dataclass(frozen=True)
class ExecutionAttestation:
    """Independent executor evidence for a frozen code/workspace run."""

    executor_id: str
    executor_version: str
    task_sha256: str
    code_sha256: str
    frozen_workspace_sha256: str
    environment_sha256: str
    sandbox_policy_sha256: str
    input_artifact_sha256: tuple[str, ...]
    output_artifact_sha256: tuple[str, ...]
    exit_code: int
    network_disabled: bool
    read_only_inputs: bool

    def __post_init__(self) -> None:
        if not self.executor_id.strip() or not self.executor_version.strip():
            raise ValueError("executor identity is required")
        for name, value in (
            ("task_sha256", self.task_sha256),
            ("code_sha256", self.code_sha256),
            ("frozen_workspace_sha256", self.frozen_workspace_sha256),
            ("environment_sha256", self.environment_sha256),
            ("sandbox_policy_sha256", self.sandbox_policy_sha256),
        ):
            _validate_sha256(name, value)
        for value in self.input_artifact_sha256:
            _validate_sha256("input_artifact_sha256", value)
        for value in self.output_artifact_sha256:
            _validate_sha256("output_artifact_sha256", value)


class SandboxExecutor(Protocol):
    executor_id: str
    executor_version: str

    def execute(
        self,
        task: CodeAgentTask,
        proposal: CodeAgentProposal,
        policy: SandboxPolicy,
    ) -> ExecutionAttestation: ...


@dataclass(frozen=True)
class MethodFidelityAttestation:
    """Independent verification that the implementation matches the locked MethodSpecification."""

    verifier_id: str
    verifier_version: str
    method_spec_sha256: str
    implementation_sha256: str
    verified_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...] = ()
    unresolved_fields: tuple[str, ...] = ()
    independent: bool = False

    def __post_init__(self) -> None:
        if not self.verifier_id.strip() or not self.verifier_version.strip():
            raise ValueError("method-fidelity verifier identity is required")
        _validate_sha256("method_spec_sha256", self.method_spec_sha256)
        _validate_sha256("implementation_sha256", self.implementation_sha256)

    @property
    def passed(self) -> bool:
        return self.independent and not self.mismatched_fields and not self.unresolved_fields


@dataclass(frozen=True)
class ReproducedCell:
    target_id: str
    value: float
    output_artifact_sha256: str

    def __post_init__(self) -> None:
        _validate_sha256("output_artifact_sha256", self.output_artifact_sha256)


@dataclass(frozen=True)
class CellComparison:
    target_id: str
    metric: str
    materiality: Materiality
    status: CellComparisonStatus
    reproduced_value: float | None
    reported_interval: tuple[float, float] | None
    output_artifact_sha256: str | None = None


@dataclass(frozen=True)
class ReproductionAgreementSummary:
    total_targets: int
    matched_targets: int
    mismatched_targets: int
    missing_targets: int
    material_mismatch_target_ids: tuple[str, ...]
    max_mismatch_materiality: Materiality | None


@dataclass(frozen=True)
class ReproductionReport:
    decision: ReproductionDecision
    comparisons: tuple[CellComparison, ...]
    agreement: ReproductionAgreementSummary
    authority: ReproductionAuthority
    max_evidence_grade: EvidenceGrade
    method_fidelity_verified: bool
    artifact_identity_verified: bool
    execution_attested: bool
    root_cause: ReproductionRootCause = ReproductionRootCause.UNKNOWN
    reasons: tuple[str, ...] = ()


def target_commitment_sha256(targets: tuple[ReproductionTarget, ...]) -> str:
    if not targets:
        raise ValueError("target commitment requires at least one target")
    target_ids = tuple(target.target_id for target in targets)
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("target ids must be unique before commitment")
    commitments = tuple(target.reference_commitment_sha256() for target in targets)
    return _stable_sha256(commitments)


def validate_target_commitment(
    task: CodeAgentTask,
    targets: tuple[ReproductionTarget, ...],
) -> None:
    target_ids = tuple(target.target_id for target in targets)
    if target_ids != task.target_ids:
        raise ValueError("unsealed target identities do not match the locked reproduction task")
    if target_commitment_sha256(targets) != task.reference_commitment_sha256:
        raise ValueError("unsealed target set does not match the locked target commitment")


def build_code_agent_task(
    *,
    task_id: str,
    mode: ReproductionMode,
    method_spec: MethodSpecification,
    artifacts: tuple[ReproductionArtifact, ...],
    targets: tuple[ReproductionTarget, ...],
    visibility_policy: AgentVisibilityPolicy | None = None,
    min_method_confidence: float = 0.95,
) -> CodeAgentTask:
    if not targets:
        raise ReproductionBlocked("reproduction requires at least one sealed target")
    missing = method_spec.missing_required_fields(min_confidence=min_method_confidence)
    if missing:
        raise ReproductionBlocked(f"method specification is incomplete or low-confidence: {missing!r}")

    policy = visibility_policy or AgentVisibilityPolicy(
        allow_original_code=mode is ReproductionMode.AUTHOR_CODE
    )
    roles = {item.role for item in artifacts}
    if not roles & {"raw_data", "analysis_data"}:
        raise ReproductionBlocked("no data artifact is available for computational reproduction")

    if mode is ReproductionMode.AUTHOR_CODE:
        if "original_code" not in roles:
            raise ReproductionBlocked("author-code reproduction requires an original_code artifact")
    else:
        if policy.allow_reported_outcomes:
            raise ReproductionBlocked("independent reimplementation must keep reported outcomes hidden")
        if policy.allow_original_code:
            raise ReproductionBlocked("independent reimplementation must keep original code hidden")
        if policy.reveal_numeric_comparison_during_iteration:
            raise ReproductionBlocked(
                "independent reimplementation may not receive numeric target-distance feedback while iterating"
            )
        artifacts = tuple(item for item in artifacts if item.role != "original_code")

    return CodeAgentTask(
        task_id=task_id,
        mode=mode,
        method_spec=method_spec,
        artifacts=artifacts,
        targets=tuple(target.blind_descriptor() for target in targets),
        reference_commitment_sha256=target_commitment_sha256(targets),
        visibility_policy=policy,
    )


def validate_agent_proposal(task: CodeAgentTask, proposal: CodeAgentProposal) -> None:
    if proposal.task_sha256 != task.sha256():
        raise ValueError("agent proposal was not produced from the locked reproduction task")
    if proposal.method_spec_sha256 != task.method_spec.sha256():
        raise ValueError("agent proposal method specification drifted")
    if proposal.visibility_policy_sha256 != task.visibility_policy.sha256():
        raise ValueError("agent proposal visibility policy drifted")
    if task.mode is ReproductionMode.AUTHOR_CODE and proposal.original_code_patch_sha256 is None:
        raise ValueError("author-code reproduction must explicitly attest the original-code patch identity")


def validate_frozen_execution(
    task: CodeAgentTask,
    proposal: CodeAgentProposal,
    policy: SandboxPolicy,
    attestation: ExecutionAttestation,
) -> None:
    validate_agent_proposal(task, proposal)
    if attestation.task_sha256 != task.sha256():
        raise ValueError("execution attestation is bound to a different task")
    if attestation.code_sha256 != proposal.generated_code_sha256:
        raise ValueError("executor did not run the frozen code proposed by the agent")
    if attestation.sandbox_policy_sha256 != policy.sha256():
        raise ValueError("execution sandbox policy drifted")
    expected_inputs = tuple(sorted(item.sha256 for item in task.artifacts))
    if tuple(sorted(attestation.input_artifact_sha256)) != expected_inputs:
        raise ValueError("execution input artifact identities do not match the locked task")
    if policy.network_disabled and not attestation.network_disabled:
        raise ValueError("execution violated the locked network-disabled policy")
    if policy.read_only_inputs and not attestation.read_only_inputs:
        raise ValueError("execution violated the locked read-only-input policy")
    if attestation.exit_code != 0:
        raise ValueError("execution did not complete successfully")


def compare_reproduced_cells(
    targets: tuple[ReproductionTarget, ...],
    reproduced: tuple[ReproducedCell, ...],
    *,
    absolute_tolerance: float = 1e-10,
    relative_tolerance: float = 1e-8,
) -> tuple[CellComparison, ...]:
    if absolute_tolerance < 0.0 or relative_tolerance < 0.0:
        raise ValueError("comparison tolerances must be non-negative")
    by_target = {item.target_id: item for item in reproduced}
    if len(by_target) != len(reproduced):
        raise ValueError("reproduced target ids must be unique")

    comparisons: list[CellComparison] = []
    for target in targets:
        cell = by_target.get(target.target_id)
        if cell is None:
            comparisons.append(
                CellComparison(
                    target.target_id,
                    target.metric,
                    target.materiality,
                    CellComparisonStatus.MISSING,
                    None,
                    None,
                    None,
                )
            )
            continue
        status, interval = _compare_number(
            target.reported,
            cell.value,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
        comparisons.append(
            CellComparison(
                target.target_id,
                target.metric,
                target.materiality,
                status,
                cell.value,
                interval,
                cell.output_artifact_sha256,
            )
        )
    return tuple(comparisons)


def summarize_reproduction_agreement(
    comparisons: tuple[CellComparison, ...],
) -> ReproductionAgreementSummary:
    mismatches = tuple(item for item in comparisons if item.status is CellComparisonStatus.MISMATCH)
    material = tuple(
        item.target_id
        for item in mismatches
        if item.materiality >= Materiality.MAIN_EMPIRICAL_CLAIM
    )
    max_materiality = max((item.materiality for item in mismatches), default=None)
    return ReproductionAgreementSummary(
        total_targets=len(comparisons),
        matched_targets=sum(item.status is CellComparisonStatus.MATCH for item in comparisons),
        mismatched_targets=len(mismatches),
        missing_targets=sum(item.status is CellComparisonStatus.MISSING for item in comparisons),
        material_mismatch_target_ids=material,
        max_mismatch_materiality=max_materiality,
    )


def build_reproduction_report(
    comparisons: tuple[CellComparison, ...],
    *,
    authority: ReproductionAuthority,
    method_fidelity_verified: bool,
    artifact_identity_verified: bool,
    execution_attested: bool,
    root_cause: ReproductionRootCause = ReproductionRootCause.UNKNOWN,
) -> ReproductionReport:
    """Build a descriptive reproduction report without E4 promotion authority.

    Callers may record verification state here, but hard reproduction contradiction authority is
    intentionally unavailable through this public builder. E4-capable construction is reserved for
    the fully validated attestation path in ``reproduction_attestation``.
    """

    return _build_reproduction_report(
        comparisons,
        authority=authority,
        method_fidelity_verified=method_fidelity_verified,
        artifact_identity_verified=artifact_identity_verified,
        execution_attested=execution_attested,
        root_cause=root_cause,
        allow_e4=False,
    )


def _build_reproduction_report(
    comparisons: tuple[CellComparison, ...],
    *,
    authority: ReproductionAuthority,
    method_fidelity_verified: bool,
    artifact_identity_verified: bool,
    execution_attested: bool,
    root_cause: ReproductionRootCause = ReproductionRootCause.UNKNOWN,
    allow_e4: bool,
) -> ReproductionReport:
    agreement = summarize_reproduction_agreement(comparisons)
    if not comparisons or all(item.status is CellComparisonStatus.MISSING for item in comparisons):
        decision = ReproductionDecision.UNVERIFIABLE
    elif any(item.status is CellComparisonStatus.MISMATCH for item in comparisons):
        decision = ReproductionDecision.MISMATCH
    elif any(item.status is CellComparisonStatus.MISSING for item in comparisons):
        decision = ReproductionDecision.PARTIAL
    else:
        decision = ReproductionDecision.MATCH

    verified_chain = method_fidelity_verified and artifact_identity_verified and execution_attested
    e4_authority = authority in {
        ReproductionAuthority.AUTHOR_PACKAGE_RERUN,
        ReproductionAuthority.INDEPENDENT_ADJUDICATED,
    }
    if decision is ReproductionDecision.MISMATCH:
        if allow_e4 and verified_chain and e4_authority:
            max_grade = EvidenceGrade.REPRODUCTION_CONTRADICTION
        else:
            max_grade = EvidenceGrade.WEAK_SIGNAL
    else:
        max_grade = EvidenceGrade.UNVERIFIABLE

    reasons: list[str] = []
    if not method_fidelity_verified:
        reasons.append("method fidelity has not been independently verified")
    if not artifact_identity_verified:
        reasons.append("input artifact identity has not been independently verified")
    if not execution_attested:
        reasons.append("sandbox execution has not been independently attested")
    if authority is ReproductionAuthority.EXPERIMENTAL_AGENT:
        reasons.append("experimental code-agent attempts cannot emit E4 evidence")
    elif e4_authority and not allow_e4:
        reasons.append("E4 reproduction authority requires the fully attested report builder")

    return ReproductionReport(
        decision=decision,
        comparisons=comparisons,
        agreement=agreement,
        authority=authority,
        max_evidence_grade=max_grade,
        method_fidelity_verified=method_fidelity_verified,
        artifact_identity_verified=artifact_identity_verified,
        execution_attested=execution_attested,
        root_cause=root_cause,
        reasons=tuple(reasons),
    )


def _compare_number(
    reported: ReportedNumber,
    reproduced: float,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> tuple[CellComparisonStatus, tuple[float, float] | None]:
    tolerance = max(absolute_tolerance, relative_tolerance * max(abs(reproduced), abs(reported.value)))
    if reported.operator is ComparisonOperator.EQ:
        low, high = reported.rounding_interval()
        matched = low - tolerance <= reproduced <= high + tolerance
        return CellComparisonStatus.MATCH if matched else CellComparisonStatus.MISMATCH, (low, high)
    if reported.operator is ComparisonOperator.LT:
        matched = reproduced < reported.value + tolerance
    elif reported.operator is ComparisonOperator.LE:
        matched = reproduced <= reported.value + tolerance
    elif reported.operator is ComparisonOperator.GT:
        matched = reproduced > reported.value - tolerance
    elif reported.operator is ComparisonOperator.GE:
        matched = reproduced >= reported.value - tolerance
    else:
        matched = False
    return CellComparisonStatus.MATCH if matched else CellComparisonStatus.MISMATCH, None
