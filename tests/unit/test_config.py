import json

import pytest
from pydantic import ValidationError

from agent import config as config_module


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_config_does_not_apply_slack_user_defaults_by_default(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "model_name": "moonshotai/Kimi-K2.6",
            "messaging": {
                "enabled": False,
                "destinations": {},
            },
        },
    )
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")

    config = config_module.load_config(str(config_path))

    assert not config.messaging.enabled
    assert config.messaging.destinations == {}


def test_load_config_applies_slack_user_defaults_from_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})
    monkeypatch.delenv("AIDD_INTERN_CLI_CONFIG", raising=False)
    monkeypatch.setattr(
        config_module,
        "DEFAULT_USER_CONFIG_PATH",
        tmp_path / "missing-user-config.json",
    )
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")

    config = config_module.load_config(str(config_path), include_user_defaults=True)

    assert config.messaging.enabled
    assert config.messaging.auto_event_types == [
        "approval_required",
        "error",
        "turn_complete",
    ]
    destination = config.messaging.destinations["slack.default"]
    assert destination.token == "xoxb-test"
    assert destination.channel == "C123"
    assert destination.allow_agent_tool
    assert destination.allow_auto_events


def test_load_config_merges_user_config_before_env_substitution(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    user_config_path = tmp_path / "user-config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})
    _write_json(
        user_config_path,
        {
            "messaging": {
                "enabled": True,
                "auto_event_types": ["approval_required"],
                "destinations": {
                    "slack.team": {
                        "provider": "slack",
                        "token": "${USER_SLACK_TOKEN}",
                        "channel": "C999",
                        "allow_agent_tool": False,
                        "allow_auto_events": True,
                    },
                },
            },
        },
    )
    monkeypatch.setenv("AIDD_INTERN_CLI_CONFIG", str(user_config_path))
    monkeypatch.setenv("AIDD_INTERN_SLACK_NOTIFICATIONS", "0")
    monkeypatch.setenv("USER_SLACK_TOKEN", "xoxb-user")

    config = config_module.load_config(str(config_path), include_user_defaults=True)

    assert config.messaging.enabled
    assert config.messaging.auto_event_types == ["approval_required"]
    assert set(config.messaging.destinations) == {"slack.team"}
    destination = config.messaging.destinations["slack.team"]
    assert destination.token == "xoxb-user"
    assert destination.channel == "C999"
    assert not destination.allow_agent_tool
    assert destination.allow_auto_events


def test_slack_user_defaults_can_be_disabled(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "model_name": "moonshotai/Kimi-K2.6",
            "messaging": {
                "enabled": False,
                "destinations": {},
            },
        },
    )
    monkeypatch.delenv("AIDD_INTERN_CLI_CONFIG", raising=False)
    monkeypatch.setattr(
        config_module,
        "DEFAULT_USER_CONFIG_PATH",
        tmp_path / "missing-user-config.json",
    )
    monkeypatch.setenv("AIDD_INTERN_SLACK_NOTIFICATIONS", "false")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")

    config = config_module.load_config(str(config_path), include_user_defaults=True)

    assert not config.messaging.enabled
    assert config.messaging.destinations == {}


def test_tool_runtime_defaults_to_local(tmp_path):
    config_path = tmp_path / "config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})

    config = config_module.load_config(str(config_path))

    assert config.tool_runtime == "local"


def test_user_config_can_set_sandbox_tool_runtime(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    user_config_path = tmp_path / "user-config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})
    _write_json(user_config_path, {"tool_runtime": "sandbox"})
    monkeypatch.setenv("AIDD_INTERN_CLI_CONFIG", str(user_config_path))

    config = config_module.load_config(str(config_path), include_user_defaults=True)

    assert config.tool_runtime == "sandbox"


def test_invalid_tool_runtime_is_rejected(tmp_path):
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {"model_name": "moonshotai/Kimi-K2.6", "tool_runtime": "hybrid"},
    )

    with pytest.raises(ValidationError):
        config_module.load_config(str(config_path))


def test_default_cli_config_registers_proteinmcp_and_local_model(monkeypatch):
    monkeypatch.setenv("AIDD_INTERN_DEFAULT_MODEL_ID", "vllm/huihui-26b")
    monkeypatch.delenv("AIDD_INTERN_WORKDIR", raising=False)

    config = config_module.load_config("configs/cli_agent_config.json")

    assert config.model_name == "vllm/huihui-26b"
    assert config.domain_pack == "aidd_binder"
    hf_mcp = config.mcpServers["hf-mcp-server"]
    bindcraft = config.mcpServers["proteinmcp-bindcraft"]
    boltzgen = config.mcpServers["proteinmcp-boltzgen"]
    pxdesign = config.mcpServers["proteinmcp-pxdesign"]
    assert hf_mcp.transport == "http"
    assert hf_mcp.url == "https://hf.co/mcp"
    assert hf_mcp.auth is None
    assert bindcraft.transport == "stdio"
    assert boltzgen.transport == "stdio"
    assert pxdesign.transport == "stdio"
    assert bindcraft.command == "bash"
    assert bindcraft.args[0] == "./scripts/run-proteinmcp-local.sh"
    assert boltzgen.args[0] == "./scripts/run-proteinmcp-local.sh"
    assert pxdesign.args[0] == "./scripts/run-proteinmcp-local.sh"
    assert bindcraft.args[-1] == "bindcraft_mcp"
    assert boltzgen.args[-1] == "boltzgen_mcp"
    assert pxdesign.args[-1] == "pxdesign_mcp"


def test_domain_pack_none_is_accepted(tmp_path):
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {"model_name": "moonshotai/Kimi-K2.6", "domain_pack": "none"},
    )

    config = config_module.load_config(str(config_path))

    assert config.domain_pack == "none"
