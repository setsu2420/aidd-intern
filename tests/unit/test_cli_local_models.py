import pytest

from agent.core import model_switcher
from agent.core.local_models import is_local_model_id
from agent.core.openai_compatible_models import is_openai_compatible_model_id
from agent.core.session import _get_max_tokens_safe, _model_info_candidates


def test_local_model_helper_accepts_supported_prefixes():
    assert is_local_model_id("ollama/llama3.1:8b")
    assert is_local_model_id("vllm/meta-llama/Llama-3.1-8B-Instruct")
    assert is_local_model_id("lm_studio/google/gemma-3-4b")
    assert is_local_model_id("llamacpp/unsloth/Qwen3.5-2B")


def test_model_switcher_accepts_supported_local_prefixes():
    assert model_switcher.is_valid_model_id("ollama/llama3.1:8b")
    assert model_switcher.is_valid_model_id("vllm/meta-llama/Llama-3.1-8B")
    assert model_switcher.is_valid_model_id("lm_studio/google/gemma-3-4b")
    assert model_switcher.is_valid_model_id("llamacpp/llama-3.1-8b")


def test_openai_compatible_model_helper_accepts_supported_prefixes():
    assert is_openai_compatible_model_id("openrouter/openai/gpt-5.2")
    assert is_openai_compatible_model_id("siliconflow/deepseek-ai/DeepSeek-V4-Flash")


def test_model_switcher_accepts_openai_compatible_prefixes():
    assert model_switcher.is_valid_model_id("openrouter/openai/gpt-5.2")
    assert model_switcher.is_valid_model_id("siliconflow/deepseek-ai/DeepSeek-V4-Flash")


def test_model_switcher_rejects_empty_or_whitespace_local_ids():
    assert not model_switcher.is_valid_model_id("ollama/")
    assert not model_switcher.is_valid_model_id("vllm/")
    assert not model_switcher.is_valid_model_id("lm_studio/")
    assert not model_switcher.is_valid_model_id("llamacpp/")
    assert not model_switcher.is_valid_model_id("ollama/llama 3.1")
    assert not model_switcher.is_valid_model_id("openrouter/")
    assert not model_switcher.is_valid_model_id("siliconflow/")
    assert not model_switcher.is_valid_model_id("openrouter/openai/gpt 5.2")


def test_model_switcher_resolves_catalog_alias(monkeypatch):
    class Catalog:
        def resolve(self, selector):
            assert selector == "flash"
            return "siliconflow/deepseek-ai/DeepSeek-V4-Flash"

    monkeypatch.setattr(model_switcher, "load_model_catalog", lambda _config: Catalog())

    assert (
        model_switcher.resolve_selector("flash", object())
        == "siliconflow/deepseek-ai/DeepSeek-V4-Flash"
    )


def test_openai_compat_prefix_is_not_supported():
    assert not model_switcher.is_valid_model_id("openai-compat/custom-model")


def test_local_models_skip_hf_router_catalog_output():
    class NoPrintConsole:
        def print(self, *args, **kwargs):
            raise AssertionError("local models should not print HF catalog info")

    assert model_switcher._print_hf_routing_info(
        "ollama/llama3.1:8b",
        NoPrintConsole(),
    )


def test_unknown_local_model_context_defaults_to_65k(monkeypatch):
    def missing_model_info(_model):
        raise Exception("unknown model")

    monkeypatch.delenv("AIDD_INTERN_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.delenv("AIDD_INTERN_LOCAL_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.setattr("litellm.main.get_model_info", missing_model_info)

    assert _get_max_tokens_safe("vllm/local-small") == 65_536


def test_unknown_remote_openai_compatible_context_uses_hosted_default(monkeypatch):
    def missing_model_info(_model):
        raise Exception("unknown model")

    monkeypatch.delenv("AIDD_INTERN_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.setattr("litellm.get_model_info", missing_model_info)

    assert _get_max_tokens_safe("openrouter/vendor/new-long-context-model") == 200_000


def test_siliconflow_deepseek_v4_flash_uses_provider_model_window(monkeypatch):
    def missing_model_info(_model):
        raise Exception("unknown model")

    monkeypatch.delenv("AIDD_INTERN_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.delenv("SILICONFLOW_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.setattr("litellm.get_model_info", missing_model_info)

    assert (
        _get_max_tokens_safe("siliconflow/deepseek-ai/DeepSeek-V4-Flash") == 1_000_000
    )


def test_openai_compatible_context_window_env_override(monkeypatch):
    def missing_model_info(_model):
        raise Exception("unknown model")

    monkeypatch.delenv("AIDD_INTERN_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.setenv("SILICONFLOW_MODEL_MAX_TOKENS", "262144")
    monkeypatch.setattr("litellm.get_model_info", missing_model_info)

    assert _get_max_tokens_safe("siliconflow/deepseek-ai/DeepSeek-V4-Flash") == 262_144


def test_openai_compatible_litellm_lookup_strips_app_prefix(monkeypatch):
    seen = []

    def fake_model_info(model):
        seen.append(model)
        if model == "openai/gpt-5.2":
            return {"max_input_tokens": 272_000}
        raise Exception("unknown model")

    monkeypatch.delenv("AIDD_INTERN_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.setattr("litellm.main.get_model_info", fake_model_info)

    assert _get_max_tokens_safe("openrouter/openai/gpt-5.2") == 272_000
    assert seen == [
        "openrouter/openai/gpt-5.2",
        "openai/gpt-5.2",
    ]


def test_model_info_candidates_strip_remote_app_prefix_and_tags():
    assert _model_info_candidates("siliconflow/deepseek-ai/DeepSeek-V4-Flash") == [
        "siliconflow/deepseek-ai/DeepSeek-V4-Flash",
        "deepseek-ai/DeepSeek-V4-Flash",
    ]
    assert _model_info_candidates("openrouter/openai/gpt-5.2") == [
        "openrouter/openai/gpt-5.2",
        "openai/gpt-5.2",
    ]


def test_context_window_env_override(monkeypatch):
    monkeypatch.delenv("AIDD_INTERN_LOCAL_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.setenv("AIDD_INTERN_MODEL_MAX_TOKENS", "32768")

    assert _get_max_tokens_safe("vllm/local-small") == 32_768


def test_local_context_window_env_override(monkeypatch):
    def missing_model_info(_model):
        raise Exception("unknown model")

    monkeypatch.delenv("AIDD_INTERN_MODEL_MAX_TOKENS", raising=False)
    monkeypatch.setenv("AIDD_INTERN_LOCAL_MODEL_MAX_TOKENS", "131072")
    monkeypatch.setattr("litellm.get_model_info", missing_model_info)

    assert _get_max_tokens_safe("vllm/local-small") == 131_072


def test_legacy_context_window_env_no_longer_caps_remote_models(
    monkeypatch,
):
    monkeypatch.setenv("AIDD_INTERN_MODEL_MAX_TOKENS", "32768")
    monkeypatch.setenv("SILICONFLOW_MODEL_MAX_TOKENS", "262144")

    assert _get_max_tokens_safe("siliconflow/deepseek-ai/DeepSeek-V4-Flash") == 262_144


def test_force_context_window_env_override_has_highest_precedence(
    monkeypatch,
):
    monkeypatch.setenv("AIDD_INTERN_MODEL_MAX_TOKENS", "131072")
    monkeypatch.setenv("AIDD_INTERN_FORCE_MODEL_MAX_TOKENS", "32768")
    monkeypatch.setenv("SILICONFLOW_MODEL_MAX_TOKENS", "262144")

    assert _get_max_tokens_safe("siliconflow/deepseek-ai/DeepSeek-V4-Flash") == 32_768


def test_openai_compatible_models_skip_hf_router_catalog_output():
    class NoPrintConsole:
        def print(self, *args, **kwargs):
            raise AssertionError("OpenAI-compatible models should not print HF info")

    assert model_switcher._print_hf_routing_info(
        "openrouter/openai/gpt-5.2",
        NoPrintConsole(),
    )


@pytest.mark.asyncio
async def test_probe_and_switch_local_model_uses_no_effort(monkeypatch):
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(model_switcher, "acompletion", fake_acompletion)

    class Config:
        model_name = "openai/gpt-5.5"
        reasoning_effort = "max"

    class Session:
        def __init__(self):
            self.model_id = None
            self.model_effective_effort = {}

        def update_model(self, model_id):
            self.model_id = model_id

    class Console:
        def print(self, *args, **kwargs):
            pass

    session = Session()
    await model_switcher.probe_and_switch_model(
        "ollama/llama3.1:8b",
        Config(),
        session,
        Console(),
        hf_token=None,
    )

    assert session.model_id == "ollama/llama3.1:8b"
    assert session.model_effective_effort["ollama/llama3.1:8b"] is None
    assert calls[0]["model"] == "openai/llama3.1:8b"
    assert "reasoning_effort" not in calls[0]
    assert "extra_body" not in calls[0]


@pytest.mark.asyncio
async def test_probe_and_switch_openai_compatible_model_uses_no_effort(
    monkeypatch,
):
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-secret")
    monkeypatch.setattr(model_switcher, "acompletion", fake_acompletion)

    class Config:
        model_name = "openai/gpt-5.5"
        reasoning_effort = "max"

    class Session:
        def __init__(self):
            self.model_id = None
            self.model_effective_effort = {}

        def update_model(self, model_id):
            self.model_id = model_id

    class Console:
        def print(self, *args, **kwargs):
            pass

    session = Session()
    await model_switcher.probe_and_switch_model(
        "openrouter/openai/gpt-5.2",
        Config(),
        session,
        Console(),
        hf_token=None,
    )

    assert session.model_id == "openrouter/openai/gpt-5.2"
    assert session.model_effective_effort["openrouter/openai/gpt-5.2"] is None
    assert calls[0]["model"] == "openai/openai/gpt-5.2"
    assert calls[0]["api_base"] == "https://openrouter.ai/api/v1"
    assert calls[0]["api_key"] == "openrouter-secret"
    assert "reasoning_effort" not in calls[0]
    assert "extra_body" not in calls[0]


@pytest.mark.asyncio
async def test_probe_and_switch_local_model_rejects_probe_errors(monkeypatch):
    async def failing_acompletion(**kwargs):
        raise ConnectionRefusedError("no server")

    monkeypatch.setattr(model_switcher, "acompletion", failing_acompletion)

    class Config:
        model_name = "openai/gpt-5.5"
        reasoning_effort = None

    class Session:
        def __init__(self):
            self.model_id = None
            self.model_effective_effort = {}

        def update_model(self, model_id):
            self.model_id = model_id

    class Console:
        def print(self, *args, **kwargs):
            pass

    config = Config()
    session = Session()
    await model_switcher.probe_and_switch_model(
        "ollama/llama3.1:8b",
        config,
        session,
        Console(),
        hf_token=None,
    )

    assert config.model_name == "openai/gpt-5.5"
    assert session.model_id is None
    assert "ollama/llama3.1:8b" not in session.model_effective_effort
