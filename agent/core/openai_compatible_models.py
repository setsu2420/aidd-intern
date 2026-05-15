"""Helpers for remote OpenAI-compatible model provider ids."""

OPENAI_COMPATIBLE_MODEL_PROVIDERS: dict[str, dict[str, str]] = {
    "openrouter/": {
        "base_url_env": "OPENROUTER_BASE_URL",
        "base_url_default": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "siliconflow/": {
        "base_url_env": "SILICONFLOW_BASE_URL",
        "base_url_default": "https://api.siliconflow.cn/v1",
        "api_key_env": "SILICONFLOW_API_KEY",
    },
}

OPENAI_COMPATIBLE_MODEL_PREFIXES = tuple(OPENAI_COMPATIBLE_MODEL_PROVIDERS)


def openai_compatible_model_provider(model_id: str) -> dict[str, str] | None:
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
