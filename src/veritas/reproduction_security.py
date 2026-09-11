from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .reproduction import CodeAgentTask

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DataSensitivity(str, Enum):
    PUBLIC = "public"
    LICENSED = "licensed"
    RESTRICTED = "restricted"
    SENSITIVE_PERSONAL = "sensitive_personal"
    UNKNOWN = "unknown"


class AgentExecutionLocation(str, Enum):
    LOCAL_SANDBOX = "local_sandbox"
    REMOTE_PROVIDER = "remote_provider"
    TRUSTED_CONFIDENTIAL_COMPUTE = "trusted_confidential_compute"


@dataclass(frozen=True)
class ArtifactAccessClassification:
    artifact_sha256: str
    sensitivity: DataSensitivity
    external_model_egress_authorized: bool = False
    basis: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_sha256, str) or not _SHA256_RE.fullmatch(self.artifact_sha256):
            raise ValueError("artifact_sha256 must be a lowercase SHA-256 hex digest")
        if not isinstance(self.sensitivity, DataSensitivity):
            raise TypeError("sensitivity must be a DataSensitivity value")
        if type(self.external_model_egress_authorized) is not bool:
            raise TypeError("external_model_egress_authorized must be a boolean")
        if not isinstance(self.basis, str):
            raise TypeError("basis must be a string")


@dataclass(frozen=True)
class AgentDispatchPolicy:
    location: AgentExecutionLocation
    provider_id: str
    confidential_compute_approved: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.location, AgentExecutionLocation):
            raise TypeError("location must be an AgentExecutionLocation value")
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ValueError("provider_id is required")
        if type(self.confidential_compute_approved) is not bool:
            raise TypeError("confidential_compute_approved must be a boolean")


class AgentDispatchBlocked(RuntimeError):
    pass


def validate_agent_dispatch(
    task: CodeAgentTask,
    classifications: tuple[ArtifactAccessClassification, ...],
    policy: AgentDispatchPolicy,
) -> None:
    """Fail closed before any task or artifact content is exposed to a coding-agent backend."""

    classified = {item.artifact_sha256: item for item in classifications}
    if len(classified) != len(classifications):
        raise AgentDispatchBlocked("artifact access classifications contain duplicate hashes")

    expected = {artifact.sha256 for artifact in task.artifacts}
    missing = tuple(sorted(expected - set(classified)))
    extra = tuple(sorted(set(classified) - expected))
    if missing or extra:
        raise AgentDispatchBlocked(
            f"artifact access classifications do not exactly match the locked task; missing={missing!r}, extra={extra!r}"
        )

    if policy.location is AgentExecutionLocation.LOCAL_SANDBOX:
        return

    if policy.location is AgentExecutionLocation.TRUSTED_CONFIDENTIAL_COMPUTE:
        if policy.confidential_compute_approved is not True:
            raise AgentDispatchBlocked("confidential compute has not been explicitly approved")
        if any(item.sensitivity is DataSensitivity.UNKNOWN for item in classifications):
            raise AgentDispatchBlocked("unknown-sensitivity artifacts cannot enter confidential compute")
        return

    unsafe: list[str] = []
    for item in classifications:
        if item.sensitivity is not DataSensitivity.PUBLIC:
            unsafe.append(f"{item.artifact_sha256}:{item.sensitivity.value}")
            continue
        if item.external_model_egress_authorized is not True:
            unsafe.append(f"{item.artifact_sha256}:public_but_egress_not_authorized")
    if unsafe:
        raise AgentDispatchBlocked(
            "remote coding-agent dispatch is restricted to public artifacts with explicit model-egress authorization: "
            + ", ".join(unsafe)
        )
