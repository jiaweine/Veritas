# ruff: noqa: B023
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from veritas.harness.model_providers import model_provider_capability, probe_model_provider
from veritas.harness.web import create_app

ROOT = Path(__file__).resolve().parents[1]


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
    assert capability["diagnostics"]["probe_supported"] is True
    assert capability["diagnostics"]["mutates_configuration"] is False
    assert capability["diagnostics"]["returns_provider_body"] is False
    assert capability["diagnostics"]["affects_detector_evidence"] is False

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


def test_provider_probe_fails_closed_before_any_network_request() -> None:
    result = asyncio.run(probe_model_provider({}))

    assert result["ok"] is False
    assert result["state"] == "not_ready"
    assert result["reachable"] is False
    assert result["status_code"] is None
    assert result["secrets_exposed"] is False
    assert result["provider_body_exposed"] is False
    assert result["affects_detector_evidence"] is False


def test_deepseek_probe_uses_server_secret_but_never_returns_it() -> None:
    secret = "deepseek-diagnostic-secret"
    seen: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"object": "list", "data": [{"id": "deepseek-chat"}]})

    result = asyncio.run(
        probe_model_provider(
            {
                "VERITAS_MODEL_PROVIDER": "deepseek",
                "VERITAS_MODEL_NAME": "deepseek-chat",
                "DEEPSEEK_API_KEY": secret,
            },
            transport=httpx.MockTransport(handler),
        )
    )

    assert result["ok"] is True
    assert result["state"] == "ready"
    assert result["provider"] == "deepseek"
    assert result["model"] == "deepseek-chat"
    assert result["status_code"] == 200
    assert result["probe_scope"] == "catalog"
    assert seen["url"] == "https://api.deepseek.com/models"
    assert seen["authorization"] == f"Bearer {secret}"
    assert secret not in repr(result)
    assert "api.deepseek.com" not in repr(result)
    assert result["provider_body_exposed"] is False
    assert result["affects_detector_evidence"] is False


def test_native_provider_probes_use_vendor_auth_shapes() -> None:
    cases = (
        (
            {
                "VERITAS_MODEL_PROVIDER": "openai",
                "VERITAS_MODEL_NAME": "gpt-test",
                "OPENAI_API_KEY": "openai-secret",
            },
            "/v1/models/gpt-test",
            "authorization",
            "Bearer openai-secret",
        ),
        (
            {
                "VERITAS_MODEL_PROVIDER": "anthropic",
                "VERITAS_MODEL_NAME": "claude-test",
                "ANTHROPIC_API_KEY": "anthropic-secret",
            },
            "/v1/models/claude-test",
            "x-api-key",
            "anthropic-secret",
        ),
        (
            {
                "VERITAS_MODEL_PROVIDER": "gemini",
                "VERITAS_MODEL_NAME": "gemini-test",
                "GEMINI_API_KEY": "gemini-secret",
            },
            "/v1beta/models/gemini-test",
            "x-goog-api-key",
            "gemini-secret",
        ),
    )

    for environ, expected_path, header_name, expected_header in cases:
        seen: dict[str, str] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["header"] = request.headers.get(header_name, "")
            if environ["VERITAS_MODEL_PROVIDER"] == "anthropic":
                seen["version"] = request.headers.get("anthropic-version", "")
            return httpx.Response(200, json={"id": environ["VERITAS_MODEL_NAME"]})

        result = asyncio.run(
            probe_model_provider(environ, transport=httpx.MockTransport(handler))
        )
        assert result["ok"] is True
        assert seen["path"] == expected_path
        assert seen["header"] == expected_header
        if environ["VERITAS_MODEL_PROVIDER"] == "anthropic":
            assert seen["version"] == "2023-06-01"
        for value in environ.values():
            if value.endswith("secret"):
                assert value not in repr(result)


def test_custom_provider_probe_keeps_endpoint_server_side() -> None:
    endpoint = "http://127.0.0.1:8123/v1"
    seen: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(429, json={"error": "rate limited"})

    result = asyncio.run(
        probe_model_provider(
            {
                "VERITAS_MODEL_PROVIDER": "custom",
                "VERITAS_MODEL_NAME": "local-research-model",
                "VERITAS_MODEL_API_KEY": "local-secret",
                "VERITAS_MODEL_BASE_URL": endpoint,
            },
            transport=httpx.MockTransport(handler),
        )
    )

    assert seen["url"] == f"{endpoint}/models"
    assert result["ok"] is False
    assert result["reachable"] is True
    assert result["authenticated"] is True
    assert result["state"] == "rate_limited"
    assert result["status_code"] == 429
    assert endpoint not in repr(result)
    assert "local-secret" not in repr(result)


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
    assert payload["diagnostics"]["probe_supported"] is True
    assert "must-not-leak" not in response.text


def test_model_provider_probe_route_returns_sanitized_diagnostic(tmp_path, monkeypatch) -> None:
    secret = "route-secret-value"
    monkeypatch.setenv("VERITAS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("VERITAS_MODEL_NAME", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)

    async def fake_probe(*args, **kwargs):
        return {
            "ok": True,
            "state": "ready",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "reachable": True,
            "authenticated": True,
            "status_code": 200,
            "latency_ms": 12.5,
            "probe_scope": "catalog",
            "detail": "Provider link accepted the configured credentials.",
            "secrets_exposed": False,
            "provider_body_exposed": False,
            "affects_detector_evidence": False,
        }

    monkeypatch.setattr("veritas.harness.model_providers.probe_model_provider", fake_probe)
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/v1/model-providers/probe")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["provider"] == "deepseek"
    assert payload["provider_body_exposed"] is False
    assert payload["affects_detector_evidence"] is False
    assert secret not in response.text


def test_cyber_provider_settings_and_browser_acceptance_are_locked() -> None:
    script = (ROOT / "src/veritas/harness/static/settings.js").read_text(encoding="utf-8")
    styles = (ROOT / "src/veritas/harness/static/settings.css").read_text(encoding="utf-8")
    shell_styles = (ROOT / "src/veritas/harness/static/settings-shell.css").read_text(
        encoding="utf-8"
    )
    interactions = (ROOT / "src/veritas/harness/static/settings-interactions.js").read_text(
        encoding="utf-8"
    )
    interaction_styles = (
        ROOT / "src/veritas/harness/static/settings-interactions.css"
    ).read_text(encoding="utf-8")
    shell = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")
    service_worker = (ROOT / "src/veritas/harness/static/sw.js").read_text(encoding="utf-8")
    browser = (ROOT / "scripts/smoke_model_providers_browser.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ui-visual-smoke.yml").read_text(encoding="utf-8")

    assert 'getJson("/api/v1/model-providers")' in script
    assert 'data-model-provider-matrix="true"' in script
    assert "Evidence firewall active" in script
    assert "ACP BRIDGE REQUIRED" in script
    assert "SERVER-ONLY" in script
    assert ".model-router" in styles
    assert ".provider-node.selected" in styles
    assert "@keyframes router-scan" in styles
    assert "@keyframes packet-flow" in styles
    assert "body:has([data-settings-surface='true']) .topbar" in shell_styles
    assert "body:has([data-settings-surface='true']) .sidebar" in shell_styles
    assert 'data-router-pointer-inspector' in interactions
    assert "pointermove" in interactions
    assert "aria-pressed" in interactions
    assert "requestAnimationFrame" in interactions
    assert 'fetch("/api/v1/model-providers/probe"' in interactions
    assert 'data-router-provider-probe' in interactions
    assert ".router-pointer-inspector" in interaction_styles
    assert ".router-probe-strip" in interaction_styles
    assert ".router-probe-button" in interaction_styles
    assert "--tilt-x" in interaction_styles
    assert "prefers-reduced-motion" in interaction_styles
    assert '/static/settings-shell.css' in shell
    assert '/static/settings-interactions.css' in shell
    assert '/static/settings-interactions.js' in shell
    assert '/static/settings-shell.css' in service_worker
    assert '/static/settings-interactions.css' in service_worker
    assert '/static/settings-interactions.js' in service_worker
    assert 'const CACHE = "veritas-shell-v26"' in service_worker
    assert '"settings-model-providers.png"' in browser
    assert '"settings-model-providers-interactive.png"' in browser
    assert '"settings-model-providers-probe.png"' in browser
    assert "SMOKE_SECRET in page.locator" in browser
    assert "replication_bridge_required" in browser
    assert "aria-pressed" in browser
    assert "python scripts/smoke_model_providers_browser.py" in workflow
    assert 'VERITAS_MODEL_PROVIDER="deepseek"' in workflow
    assert 'DEEPSEEK_API_KEY="veritas-browser-smoke-secret"' in workflow
