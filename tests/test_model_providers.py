from __future__ import annotations

from fastapi.testclient import TestClient

from veritas.harness.model_providers import model_provider_capability
from veritas.harness.web import create_app


def test_model_provider_registry_is_explicit_and_secret_free() -> None:
    capability = model_provider_capability({})

    assert capability["selected_provider"] is None
    assert capability["active_ready"] is False
    assert capability["selection_valid"] is True
    assert capability["browser_writable"] is False
    assert capability["secrets_exposed"] is False
    assert capability["direct_detector_access"] is False
    assert capability["replication_bridge_required"] is True
    assert capability["replication_transport"] == "acp"

    providers = {item["provider_id"]: item for item in capability["providers"]}
    assert set(providers) == {
        "openai",
        "deepseek",
        "anthropic",
        "gemini",
        "openai_compatible",
    }
    assert providers["openai"]["api_key_env"] == "OPENAI_API_KEY"
    assert providers["deepseek"]["api_key_env"] == "DEEPSEEK_API_KEY"
    assert all(item["state"] == "available" for item in providers.values())


def test_deepseek_provider_can_be_selected_without_exposing_key() -> None:
    secret = "deepseek-super-secret-value"
    capability = model_provider_capability(
        {
            "VERITAS_MODEL_PROVIDER": "deepseek",
            "VERITAS_MODEL_NAME": "deepseek-chat",
            "DEEPSEEK_API_KEY": secret,
        }
    )

    assert capability["selected_provider"] == "deepseek"
    assert capability["model"] == "deepseek-chat"
    assert capability["active_ready"] is True
    selected = next(item for item in capability["providers"] if item["selected"])
    assert selected["provider_id"] == "deepseek"
    assert selected["api_style"] == "openai-compatible"
    assert selected["key_configured"] is True
    assert selected["endpoint_configured"] is True
    assert secret not in repr(capability)


def test_generic_openai_compatible_provider_requires_custom_endpoint() -> None:
    incomplete = model_provider_capability(
        {
            "VERITAS_MODEL_PROVIDER": "custom",
            "VERITAS_MODEL_NAME": "local-research-model",
            "VERITAS_MODEL_API_KEY": "placeholder",
        }
    )
    selected = next(item for item in incomplete["providers"] if item["selected"])
    assert selected["provider_id"] == "openai_compatible"
    assert selected["state"] == "missing_endpoint"
    assert incomplete["active_ready"] is False

    ready = model_provider_capability(
        {
            "VERITAS_MODEL_PROVIDER": "openai-compatible",
            "VERITAS_MODEL_NAME": "local-research-model",
            "VERITAS_MODEL_API_KEY": "placeholder",
            "VERITAS_MODEL_BASE_URL": "http://127.0.0.1:8000/v1",
        }
    )
    selected = next(item for item in ready["providers"] if item["selected"])
    assert selected["state"] == "ready"
    assert ready["active_ready"] is True
    assert "127.0.0.1" not in repr(ready)


def test_unsupported_provider_fails_closed() -> None:
    capability = model_provider_capability(
        {
            "VERITAS_MODEL_PROVIDER": "mystery-provider",
            "VERITAS_MODEL_NAME": "model-x",
            "VERITAS_MODEL_API_KEY": "secret",
        }
    )

    assert capability["selected_provider"] is None
    assert capability["requested_provider"] == "mystery-provider"
    assert capability["selection_valid"] is False
    assert capability["active_ready"] is False
    assert capability["model"] is None


def test_model_provider_api_returns_only_redacted_control_plane_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_MODEL_PROVIDER", "gpt")
    monkeypatch.setenv("VERITAS_MODEL_NAME", "gpt-research")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/v1/model-providers")
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_provider"] == "openai"
    assert payload["model"] == "gpt-research"
    assert payload["active_ready"] is True
    assert payload["secrets_exposed"] is False
    assert "must-not-leak" not in response.text
