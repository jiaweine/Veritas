from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .reproduction import SandboxPolicy

_IMAGE_DIGEST_RE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")


class ReplicationRuntime(str, Enum):
    PYTHON = "python"
    R = "r"
    STATA = "stata"


class IsolationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ReplicationRunnerSpec:
    runtime: ReplicationRuntime
    image_ref: str
    entrypoint: str
    dependency_lock_sha256: str
    stata_license_authorized: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, ReplicationRuntime):
            raise TypeError("runtime must be a ReplicationRuntime")
        if not isinstance(self.image_ref, str) or not _IMAGE_DIGEST_RE.fullmatch(self.image_ref):
            raise ValueError("image_ref must be pinned by an explicit sha256 image digest")
        if not isinstance(self.entrypoint, str) or not self.entrypoint.strip():
            raise ValueError("replication entrypoint is required")
        path = Path(self.entrypoint)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("replication entrypoint must stay within the read-only source mount")
        if not re.fullmatch(r"[0-9a-f]{64}", self.dependency_lock_sha256):
            raise ValueError("dependency_lock_sha256 must be a lowercase SHA-256 hex digest")
        if type(self.stata_license_authorized) is not bool:
            raise TypeError("stata_license_authorized must be a boolean")
        if self.runtime is ReplicationRuntime.STATA and not self.stata_license_authorized:
            raise ValueError("Stata runner requires explicit licensed-runtime authorization")


@dataclass(frozen=True)
class IsolatedRunResult:
    command: tuple[str, ...]
    exit_code: int
    source_tree_sha256: str
    output_tree_sha256: str
    network_disabled: bool
    read_only_inputs: bool


@dataclass(frozen=True)
class ContainerIsolationBackend:
    """OCI runner that enforces the v0.13 isolation contract at command construction time.

    The backend is executable when Docker or a Docker-compatible CLI is available. Tests can
    inspect the generated command without requiring a container daemon.
    """

    binary: str = "docker"
    executor_id: str = "veritas-oci-runner"
    executor_version: str = "1"

    def build_command(
        self,
        spec: ReplicationRunnerSpec,
        *,
        source_dir: str | Path,
        output_dir: str | Path,
        policy: SandboxPolicy | None = None,
    ) -> tuple[str, ...]:
        locked_policy = policy or SandboxPolicy()
        _require_secure_policy(locked_policy)

        source = Path(source_dir).resolve()
        output = Path(output_dir).resolve()
        if not source.is_dir():
            raise ValueError("source_dir must exist and be a directory")
        output.mkdir(parents=True, exist_ok=True)
        entrypoint = source / spec.entrypoint
        if not entrypoint.is_file():
            raise ValueError("replication entrypoint does not exist inside source_dir")

        runtime_command = _runtime_command(spec)
        command = (
            self.binary,
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "256",
            "--cpus",
            str(locked_policy.max_cpus),
            "--memory",
            f"{locked_policy.max_memory_mb}m",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=512m",
            "--tmpfs",
            "/work:rw,nosuid,nodev,size=1024m",
            "--mount",
            f"type=bind,src={source},dst=/input,readonly",
            "--mount",
            f"type=bind,src={output},dst=/output",
            "--workdir",
            "/work",
            "--env",
            "VERITAS_INPUT_DIR=/input",
            "--env",
            "VERITAS_OUTPUT_DIR=/output",
            spec.image_ref,
            *runtime_command,
        )
        return command

    def execute(
        self,
        spec: ReplicationRunnerSpec,
        *,
        source_dir: str | Path,
        output_dir: str | Path,
        policy: SandboxPolicy | None = None,
    ) -> IsolatedRunResult:
        locked_policy = policy or SandboxPolicy()
        command = self.build_command(
            spec,
            source_dir=source_dir,
            output_dir=output_dir,
            policy=locked_policy,
        )
        source = Path(source_dir).resolve()
        output = Path(output_dir).resolve()
        source_before = tree_sha256(source)
        try:
            completed = subprocess.run(
                command,
                check=False,
                timeout=locked_policy.max_wall_seconds,
                env=_minimal_host_environment(),
            )
        except FileNotFoundError as exc:
            raise IsolationUnavailable(f"container runtime not available: {self.binary!r}") from exc
        except subprocess.TimeoutExpired as exc:
            raise IsolationUnavailable("isolated replication exceeded locked wall-time limit") from exc

        source_after = tree_sha256(source)
        if source_after != source_before:
            raise RuntimeError("read-only replication source tree changed during isolated execution")
        return IsolatedRunResult(
            command=command,
            exit_code=completed.returncode,
            source_tree_sha256=source_before,
            output_tree_sha256=tree_sha256(output),
            network_disabled=True,
            read_only_inputs=True,
        )


def tree_sha256(path: str | Path) -> str:
    root = Path(path)
    if not root.is_dir():
        raise ValueError("tree_sha256 requires a directory")
    digest = hashlib.sha256()
    for item in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        relative = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        payload = item.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _runtime_command(spec: ReplicationRunnerSpec) -> tuple[str, ...]:
    entrypoint = f"/input/{Path(spec.entrypoint).as_posix()}"
    if spec.runtime is ReplicationRuntime.PYTHON:
        return ("python", entrypoint)
    if spec.runtime is ReplicationRuntime.R:
        return ("Rscript", "--vanilla", entrypoint)
    if spec.runtime is ReplicationRuntime.STATA:
        return ("stata-mp", "-b", "do", entrypoint)
    raise ValueError(f"unsupported replication runtime: {spec.runtime!r}")


def _require_secure_policy(policy: SandboxPolicy) -> None:
    if policy.network_disabled is not True:
        raise ValueError("isolated replication runner requires network_disabled=True")
    if policy.read_only_inputs is not True:
        raise ValueError("isolated replication runner requires read_only_inputs=True")


def _minimal_host_environment() -> dict[str, str]:
    allowed = ("PATH", "HOME", "DOCKER_HOST", "XDG_RUNTIME_DIR")
    return {name: os.environ[name] for name in allowed if name in os.environ}
