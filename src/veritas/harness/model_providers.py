from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelProviderDescriptor:
    provider_id: str
    label: str
    family: str
    api_style: str
    api_key_env: str
    default_endpoint: bool
    notes: str


_PROVIDER_CATALOG: tuple[ModelProviderDescriptor, ...] = (
    ModelProviderDescriptor(
        provider_id="openai",
        label="OpenAI",
        family="GPT",
        api_style="responses",
        api_key_env="OPENAI_API_KEY",
        default_endpoint=True,
        notes="Native OpenAI model endpoint.",
    ),
    ModelProviderDescriptor(
        provider_id="deepseek",
        label="DeepSeek",
        family="DeepSeek",
        api_style="openai-compatible",
        api_key_env="DEEPSEEK_API_KEY",
        default_endpoint=True,
        notes="OpenAI-compatible provider adapter.",
    ),
    ModelProviderDescriptor(
        provider_id="anthropic",
        label="Anthropic",
        family="Claude",
        api_style="messages",
        api_key_env="ANTHROPIC_API_KEY",
        default_endpoint=True,
        notes="Anthropic Messages-style provider adapter.",
    ),
    ModelProviderDescriptor(
        provider_id="gemini",
        label="Google Gemini",
        family="Gemini",
        api_style="generate-content",
        api_key_env="GEMINI_API_KEY",
        default_endpoint=True,
        notes="Google Gemini provider adapter.",
    ),
    ModelProviderDescriptor(
        provider_id="openai_compatible",
        label="OpenAI-compatible",
        family="Custom / routed",
        api_style="openai-compatible",
        api_key_env="VERITAS_MODEL_API_KEY",
        default_endpoint=False,
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
        "configuration": {
            "provider_env": "VERITAS_MODEL_PROVIDER",
            "model_env": "VERITAS_MODEL_NAME",
            "base_url_env": "VERITAS_MODEL_BASE_URL",
        },
    }
