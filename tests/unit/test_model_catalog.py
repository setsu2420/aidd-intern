import json

from agent.core.model_catalog import (
    load_model_catalog,
    resolve_model_selector,
    set_default_model,
)


def _write_catalog(path):
    path.write_text(
        json.dumps(
            {
                "default": "openrouter/openai/gpt-5.2",
                "models": [
                    {
                        "id": "openrouter/openai/gpt-5.2",
                        "label": "GPT via OpenRouter",
                        "provider": "openrouter",
                        "tier": "external",
                        "aliases": ["gpt"],
                    },
                    {
                        "id": "siliconflow/deepseek-ai/DeepSeek-V4-Flash",
                        "label": "DeepSeek Flash",
                        "provider": "siliconflow",
                        "tier": "external",
                        "aliases": ["flash"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_model_catalog_loads_default_aliases_and_numbered_selectors(tmp_path):
    path = tmp_path / "models.json"
    _write_catalog(path)
    config = type("Config", (), {"models_config": str(path)})()

    catalog = load_model_catalog(config)

    assert catalog.default == "openrouter/openai/gpt-5.2"
    assert catalog.resolve("1") == "openrouter/openai/gpt-5.2"
    assert catalog.resolve("flash") == "siliconflow/deepseek-ai/DeepSeek-V4-Flash"
    assert resolve_model_selector("gpt", config) == "openrouter/openai/gpt-5.2"


def test_model_catalog_writes_default_without_touching_models(tmp_path):
    path = tmp_path / "models.json"
    _write_catalog(path)
    config = type("Config", (), {"models_config": str(path)})()

    saved_path = set_default_model("siliconflow/deepseek-ai/DeepSeek-V4-Flash", config)

    assert saved_path == path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["default"] == "siliconflow/deepseek-ai/DeepSeek-V4-Flash"
    assert len(payload["models"]) == 2
