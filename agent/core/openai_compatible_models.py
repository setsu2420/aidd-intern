"""Helpers for remote OpenAI-compatible model provider ids."""

from __future__ import annotations

import os


OPENAI_COMPATIBLE_MODEL_PROVIDERS: dict[str, dict[str, str | int]] = {
    "openrouter/": {
        "base_url_env": "OPENROUTER_BASE_URL",
        "base_url_default": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "max_tokens_env": "OPENROUTER_MODEL_MAX_TOKENS",
    },
    "siliconflow/": {
        "base_url_env": "SILICONFLOW_BASE_URL",
        "base_url_default": "https://api.siliconflow.cn/v1",
        "api_key_env": "SILICONFLOW_API_KEY",
        "max_tokens_env": "SILICONFLOW_MODEL_MAX_TOKENS",
        "model_max_tokens": {
            # SiliconFlow advertises DeepSeek-V4-Flash as a 1M-token model.
            # Keep this scoped to the known model so other SiliconFlow models
            # can fall back to the generic hosted default unless configured.
            "deepseek-ai/DeepSeek-V4-Flash": 1_000_000,
        },
    },
}

OPENAI_COMPATIBLE_MODEL_PREFIXES = tuple(OPENAI_COMPATIBLE_MODEL_PROVIDERS)


def openai_compatible_model_provider(model_id: str) -> dict[str, str | int] | None:
    """Return provider config for a remote OpenAI-compatible model id."""
    for prefix, config in OPENAI_COMPATIBLE_MODEL_PROVIDERS.items():
        if model_id.startswith(prefix):
            return config
    return None


def openai_compatible_model_name(model_id: str) -> str | None:
    """Return the provider model name with the app prefix removed."""
    for prefix in OPENAI_COMPATIBLE_MODEL_PREFIXES:
        if model_id.startswith(prefix):
            name = model_id[len(prefix) :]
            return name or None
    return None


def is_openai_compatible_model_id(model_id: str) -> bool:
    """Return True for non-empty, whitespace-free remote provider model ids."""
    if not model_id or any(char.isspace() for char in model_id):
        return False
    return openai_compatible_model_name(model_id) is not None


def _parse_positive_int_env(env_name: str) -> int | None:
    value = os.environ.get(env_name, "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def openai_compatible_context_window(model_id: str) -> int | None:
    """Return provider-configured context window for a remote compatible model.

    Per-provider environment overrides win over defaults so operators can tune
    newly connected providers without waiting for LiteLLM catalog support.
    """
    provider = openai_compatible_model_provider(model_id)
    if provider is None:
        return None

    env_name = provider.get("max_tokens_env")
    if isinstance(env_name, str):
        override = _parse_positive_int_env(env_name)
        if override is not None:
            return override

    provider_model = openai_compatible_model_name(model_id)
    model_defaults = provider.get("model_max_tokens")
    if isinstance(provider_model, str) and isinstance(model_defaults, dict):
        bare_model = provider_model.split(":", 1)[0]
        default = model_defaults.get(bare_model)
        if isinstance(default, int) and default > 0:
            return default

    return None
