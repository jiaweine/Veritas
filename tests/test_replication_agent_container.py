"""Containerized OS-tool execution remains an explicit, bounded ACP opt-in."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from veritas.replication import AcpTurnRunner, AgentCommand, agent_from_environment

IMAGE = "example.local/veritas-acp@sha256:" + "a" * 64


def test_normal_acp_agent_keeps_existing_process_behavior(tmp_path: Path) -> None:
    agent = AgentCommand(argv=("my-agent", "--stdio"))
    argv, cwd, env = AcpTurnRunner(agent)._launch_spec(tmp_path.resolve())

    assert argv == ("my-agent", "--stdio")
    assert cwd == str(tmp_path.resolve())
    assert "UNRELATED_SECRET" not in env


def test_constrained_container_command_does_not_expose_host_or_secret_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_KEY_FOR_AGENT", "private-credential")
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-inherit")
    agent = AgentCommand(
        argv=("coding-agent", "--acp"),
        container_image=IMAGE,
        forward_env=("MODEL_KEY_FOR_AGENT",),
    )

    argv, cwd, env = AcpTurnRunner(agent)._launch_spec(tmp_path.resolve())
    assert argv[:3] == ("docker", "run", "--rm")
    assert cwd == "/workspace"
    assert "--interactive" in argv
    assert "--read-only" in argv
    assert ("--cap-drop", "ALL") == (argv[argv.index("--cap-drop")], argv[argv.index("--cap-drop") + 1])
    assert ("--network", "none") == (argv[argv.index("--network")], argv[argv.index("--network") + 1])
    assert ("--security-opt", "no-new-privileges") == (
        argv[argv.index("--security-opt")], argv[argv.index("--security-opt") + 1]
    )
    assert f"{tmp_path.resolve()}:/workspace:rw" in argv
    assert argv[-3:] == (IMAGE, "coding-agent", "--acp")
    assert argv.count("--volume") == 1
    assert "MODEL_KEY_FOR_AGENT" in argv
    assert "private-credential" not in argv
    assert "UNRELATED_SECRET" not in env
    assert env["MODEL_KEY_FOR_AGENT"] == "private-credential"
    assert "--privileged" not in argv
    assert "/var/run/docker.sock" not in str(argv)


def test_opt_in_network_is_bridge_only(tmp_path: Path) -> None:
    agent = AgentCommand(
        argv=("agent",), container_image=IMAGE, container_network="bridge"
    )
    argv, _, _ = AcpTurnRunner(agent)._launch_spec(tmp_path.resolve())
    assert argv[argv.index("--network") + 1] == "bridge"


@pytest.mark.parametrize(
    ("image", "network"),
    [
        ("", "none"),
        ("busybox:latest", "none"),
        ("-untrusted@sha256:" + "a" * 64, "none"),
        ("repo@sha256:" + "z" * 64, "none"),
        (IMAGE, "host"),
        (IMAGE, "container:danger"),
    ],
)
def test_container_config_rejects_unpinned_or_privileged_values(image: str, network: str) -> None:
    with pytest.raises(ValueError):
        AgentCommand(argv=("agent",), container_image=image, container_network=network)


def test_agent_from_environment_keeps_opt_in_container_when_model_is_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "code-agent --acp")
    monkeypatch.setenv("VERITAS_REPLICATION_CONTAINER_IMAGE", IMAGE)
    monkeypatch.setenv("VERITAS_REPLICATION_CONTAINER_NETWORK", "none")
    monkeypatch.setenv("VERITAS_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("VERITAS_MODEL_NAME", "example")
    monkeypatch.setenv("OPENAI_API_KEY", "only-for-server-process")
    monkeypatch.setenv("UNRELATED_SECRET", "not-in-container")
    agent = agent_from_environment()
    assert agent is not None
    assert agent.container_image == IMAGE
    assert agent.container_network == "none"
    assert "OPENAI_API_KEY" in agent.forward_env
    assert "UNRELATED_SECRET" not in agent.forward_env
    assert os.environ["UNRELATED_SECRET"] == "not-in-container"
