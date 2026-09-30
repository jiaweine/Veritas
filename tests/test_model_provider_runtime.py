from __future__ import annotations

from veritas.replication import agent_from_environment


def test_selected_provider_is_bound_into_acp_process_without_other_provider_secrets(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "python -m veritas_fake_agent")
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT_NAME", "Test ACP agent")
    monkeypatch.setenv("VERITAS_REPLICATION_FORWARD_ENV", "EXISTING_ALLOWED")
    monkeypatch.setenv("EXISTING_ALLOWED", "kept")
    monkeypatch.setenv("VERITAS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("VERITAS_MODEL_NAME", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "selected-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-forward")

    agent = agent_from_environment()

    assert agent is not None
    assert agent.name == "Test ACP agent"
    assert agent.argv == ("python", "-m", "veritas_fake_agent")
    assert "EXISTING_ALLOWED" in agent.forward_env
    assert "VERITAS_MODEL_PROVIDER" in agent.forward_env
    assert "VERITAS_MODEL_NAME" in agent.forward_env
    assert "DEEPSEEK_API_KEY" in agent.forward_env
    assert "OPENAI_API_KEY" not in agent.forward_env

    process_env = agent.process_env()
    assert process_env["EXISTING_ALLOWED"] == "kept"
    assert process_env["DEEPSEEK_API_KEY"] == "selected-secret"
    assert process_env["VERITAS_MODEL_PROVIDER"] == "deepseek"
    assert process_env["VERITAS_MODEL_NAME"] == "deepseek-chat"
    assert process_env["VERITAS_MODEL_PROVIDER_RESOLVED"] == "deepseek"
    assert process_env["VERITAS_MODEL_API_STYLE"] == "openai-compatible"
    assert "OPENAI_API_KEY" not in process_env
    assert "must-not-forward" not in repr(process_env)


def test_incomplete_provider_is_not_forwarded_to_acp_process(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "python -m veritas_fake_agent")
    monkeypatch.setenv("VERITAS_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("VERITAS_MODEL_NAME", "gpt-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = agent_from_environment()

    assert agent is not None
    assert "VERITAS_MODEL_PROVIDER" not in agent.forward_env
    assert "VERITAS_MODEL_NAME" not in agent.forward_env
    assert "OPENAI_API_KEY" not in agent.forward_env
    process_env = agent.process_env()
    assert "VERITAS_MODEL_PROVIDER_RESOLVED" not in process_env
    assert "VERITAS_MODEL_API_STYLE" not in process_env


def test_custom_provider_requires_server_endpoint_before_acp_binding(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_REPLICATION_AGENT", "python -m veritas_fake_agent")
    monkeypatch.setenv("VERITAS_MODEL_PROVIDER", "custom")
    monkeypatch.setenv("VERITAS_MODEL_NAME", "local-model")
    monkeypatch.setenv("VERITAS_MODEL_API_KEY", "custom-secret")
    monkeypatch.delenv("VERITAS_MODEL_BASE_URL", raising=False)

    unbound = agent_from_environment()
    assert unbound is not None
    assert "VERITAS_MODEL_API_KEY" not in unbound.forward_env

    monkeypatch.setenv("VERITAS_MODEL_BASE_URL", "http://127.0.0.1:9000/v1")
    bound = agent_from_environment()
    assert bound is not None
    assert "VERITAS_MODEL_API_KEY" in bound.forward_env
    assert "VERITAS_MODEL_BASE_URL" in bound.forward_env
    process_env = bound.process_env()
    assert process_env["VERITAS_MODEL_PROVIDER_RESOLVED"] == "openai_compatible"
    assert process_env["VERITAS_MODEL_API_STYLE"] == "openai-compatible"
