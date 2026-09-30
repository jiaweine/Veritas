from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI


@dataclass(frozen=True)
class ModelProviderDescriptor:
    provider_id: str
    label: str
    family: str
    api_style: str
    api_key_env: str
    default_endpoint: bool
    default_base_url: str | None
    probe_scope: str
    notes: str


_PROVIDER_CATALOG: tuple[ModelProviderDescriptor, ...] = (
    ModelProviderDescriptor(
        provider_id="openai",
        label="OpenAI",
        family="GPT",
        api_style="responses",
        api_key_env="OPENAI_API_KEY",
        default_endpoint=True,
        default_base_url="https://api.openai.com/v1",
        probe_scope="model",
        notes="Native OpenAI model endpoint.",
    ),
    ModelProviderDescriptor(
        provider_id="deepseek",
        label="DeepSeek",
        family="DeepSeek",
        api_style="openai-compatible",
        api_key_env="DEEPSEEK_API_KEY",
        default_endpoint=True,
        default_base_url="https://api.deepseek.com",
        probe_scope="catalog",
        notes="OpenAI-compatible provider adapter.",
    ),
    ModelProviderDescriptor(
        provider_id="anthropic",
        label="Anthropic",
        family="Claude",
        api_style="messages",
        api_key_env="ANTHROPIC_API_KEY",
        default_endpoint=True,
        default_base_url="https://api.anthropic.com/v1",
        probe_scope="model",
        notes="Anthropic Messages-style provider adapter.",
    ),
    ModelProviderDescriptor(
        provider_id="gemini",
        label="Google Gemini",
        family="Gemini",
        api_style="generate-content",
        api_key_env="GEMINI_API_KEY",
        default_endpoint=True,
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        probe_scope="model",
        notes="Google Gemini provider adapter.",
    ),
    ModelProviderDescriptor(
        provider_id="openai_compatible",
        label="OpenAI-compatible",
        family="Custom / routed",
        api_style="openai-compatible",
        api_key_env="VERITAS_MODEL_API_KEY",
        default_endpoint=False,
        default_base_url=None,
        probe_scope="catalog",
        notes="Generic endpoint for gateways, hosted inference, or self-hosted servers.",
    ),
)

_PROVIDER_ALIASES = {
    "gpt": "openai",
    "claude": "anthropic",
    "google": "gemini",
    "custom": "openai_compatible",
    "openai-compatible": "openai_compatible",
}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _descriptor(provider_id: str | None) -> ModelProviderDescriptor | None:
    return next((item for item in _PROVIDER_CATALOG if item.provider_id == provider_id), None)


def _selected_provider_id(environ: Mapping[str, str]) -> tuple[str | None, str | None]:
    requested = _clean(environ.get("VERITAS_MODEL_PROVIDER")).casefold()
    if not requested:
        return None, None
    normalized = _PROVIDER_ALIASES.get(requested, requested)
    if normalized not in {item.provider_id for item in _PROVIDER_CATALOG}:
        return None, requested
    return normalized, requested


def _provider_state(
    descriptor: ModelProviderDescriptor,
    *,
    selected_id: str | None,
    model: str,
    base_url: str,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    selected = descriptor.provider_id == selected_id
    key_configured = bool(_clean(environ.get(descriptor.api_key_env)))
    endpoint_configured = descriptor.default_endpoint or bool(base_url)
    model_configured = bool(model) if selected else False

    if not selected:
        state = "available"
    elif not model_configured:
        state = "missing_model"
    elif not key_configured:
        state = "missing_key"
    elif not endpoint_configured:
        state = "missing_endpoint"
    else:
        state = "ready"

    return {
        "provider_id": descriptor.provider_id,
        "label": descriptor.label,
        "family": descriptor.family,
        "api_style": descriptor.api_style,
        "api_key_env": descriptor.api_key_env,
        "selected": selected,
        "state": state,
        "key_configured": key_configured,
        "model_configured": model_configured,
        "endpoint_configured": endpoint_configured,
        "endpoint_mode": "provider_default" if descriptor.default_endpoint else "custom_required",
        "notes": descriptor.notes,
    }


def model_provider_capability(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Expose non-secret model-provider control-plane state.

    Veritas deliberately keeps this registry separate from detector evidence and
    from the ACP execution transport. Provider credentials are consumed only by
    a server-side adapter/agent and are never returned through this capability.
    """

    source = os.environ if environ is None else environ
    selected_id, requested = _selected_provider_id(source)
    model = _clean(source.get("VERITAS_MODEL_NAME"))
    base_url = _clean(source.get("VERITAS_MODEL_BASE_URL"))
    providers = [
        _provider_state(
            descriptor,
            selected_id=selected_id,
            model=model,
            base_url=base_url,
            environ=source,
        )
        for descriptor in _PROVIDER_CATALOG
    ]
    active = next((item for item in providers if item["selected"]), None)
    ready = bool(active and active["state"] == "ready")

    return {
        "selected_provider": selected_id,
        "requested_provider": requested,
        "selection_valid": requested is None or selected_id is not None,
        "model": model if selected_id else None,
        "active_ready": ready,
        "providers": providers,
        "browser_writable": False,
        "server_configured": True,
        "secrets_exposed": False,
        "direct_detector_access": False,
        "replication_bridge_required": True,
        "replication_transport": "acp",
        "diagnostics": {
            "probe_supported": True,
            "mutates_configuration": False,
            "returns_provider_body": False,
            "affects_detector_evidence": False,
        },
        "configuration": {
            "provider_env": "VERITAS_MODEL_PROVIDER",
            "model_env": "VERITAS_MODEL_NAME",
            "base_url_env": "VERITAS_MODEL_BASE_URL",
        },
    }


def _probe_url(
    descriptor: ModelProviderDescriptor,
    *,
    model: str,
    base_url: str,
) -> str:
    root = (base_url or descriptor.default_base_url or "").rstrip("/")
    if not root:
        raise ValueError("provider endpoint is not configured")
    encoded_model = quote(model, safe="")
    if descriptor.provider_id in {"openai", "anthropic", "gemini"}:
        return f"{root}/models/{encoded_model}"
    return f"{root}/models"


def _probe_headers(
    descriptor: ModelProviderDescriptor,
    *,
    api_key: str,
) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Veritas/provider-diagnostic",
    }
    if descriptor.provider_id == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif descriptor.provider_id == "gemini":
        headers["x-goog-api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def probe_model_provider(
    environ: Mapping[str, str] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout_seconds: float = 6.0,
) -> dict[str, Any]:
    """Perform a bounded, non-generative provider reachability/auth probe.

    The browser never supplies an endpoint, model, or credential to this
    function. All routing comes from trusted server configuration. The probe
    returns only sanitized status metadata: response bodies, credentials, and
    custom endpoint values are deliberately discarded.
    """

    source = os.environ if environ is None else environ
    capability = model_provider_capability(source)
    provider_id = capability.get("selected_provider")
    model = _clean(capability.get("model"))
    descriptor = _descriptor(str(provider_id) if provider_id else None)

    if descriptor is None or not capability.get("active_ready"):
        return {
            "ok": False,
            "state": "not_ready",
            "provider": provider_id,
            "model": model or None,
            "reachable": False,
            "authenticated": False,
            "status_code": None,
            "latency_ms": None,
            "probe_scope": descriptor.probe_scope if descriptor else None,
            "detail": "Complete the server-side provider configuration before testing the link.",
            "secrets_exposed": False,
            "provider_body_exposed": False,
            "affects_detector_evidence": False,
        }

    api_key = _clean(source.get(descriptor.api_key_env))
    base_url = _clean(source.get("VERITAS_MODEL_BASE_URL"))
    try:
        url = _probe_url(descriptor, model=model, base_url=base_url)
    except ValueError:
        return {
            "ok": False,
            "state": "not_ready",
            "provider": descriptor.provider_id,
            "model": model,
            "reachable": False,
            "authenticated": False,
            "status_code": None,
            "latency_ms": None,
            "probe_scope": descriptor.probe_scope,
            "detail": "The selected provider endpoint is not configured.",
            "secrets_exposed": False,
            "provider_body_exposed": False,
            "affects_detector_evidence": False,
        }

    started = perf_counter()
    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        ) as client:
            response = await client.get(url, headers=_probe_headers(descriptor, api_key=api_key))
    except httpx.RequestError as exc:
        return {
            "ok": False,
            "state": "unreachable",
            "provider": descriptor.provider_id,
            "model": model,
            "reachable": False,
            "authenticated": False,
            "status_code": None,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "probe_scope": descriptor.probe_scope,
            "error_type": type(exc).__name__,
            "detail": "The provider endpoint could not be reached.",
            "secrets_exposed": False,
            "provider_body_exposed": False,
            "affects_detector_evidence": False,
        }

    status_code = int(response.status_code)
    ok = 200 <= status_code < 300
    authenticated = status_code not in {401, 403}
    if ok:
        state = "ready"
        detail = "Provider link accepted the configured credentials."
    elif status_code in {401, 403}:
        state = "auth_rejected"
        detail = "The provider rejected the configured credentials."
    elif status_code == 404:
        state = "model_or_endpoint_missing"
        detail = "The provider is reachable but the configured model or diagnostic endpoint was not found."
    elif status_code == 429:
        state = "rate_limited"
        detail = "The provider is reachable but rate-limited the diagnostic request."
    else:
        state = "provider_error"
        detail = "The provider returned a non-success diagnostic response."

    return {
        "ok": ok,
        "state": state,
        "provider": descriptor.provider_id,
        "model": model,
        "reachable": True,
        "authenticated": authenticated,
        "status_code": status_code,
        "latency_ms": round((perf_counter() - started) * 1000, 2),
        "probe_scope": descriptor.probe_scope,
        "detail": detail,
        "secrets_exposed": False,
        "provider_body_exposed": False,
        "affects_detector_evidence": False,
    }


def register_model_provider_routes(app: FastAPI) -> None:
    @app.get("/api/v1/model-providers")
    def get_model_providers() -> dict[str, Any]:
        return model_provider_capability()

    @app.post("/api/v1/model-providers/probe")
    async def post_model_provider_probe() -> dict[str, Any]:
        return await probe_model_provider()
