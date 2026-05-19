from types import SimpleNamespace
from unittest.mock import patch

from litellm import Message

from agent.context_manager import manager


def test_hf_username_lookup_is_cached(monkeypatch):
    calls = 0

    def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=0, stdout='{"name":"alice"}')

    manager._hf_username_cache.clear()
    monkeypatch.setattr("subprocess.run", fake_run)

    assert manager._get_hf_username("hf_test_token") == "alice"
    assert manager._get_hf_username("hf_test_token") == "alice"
    assert calls == 1


def test_estimate_usage_uses_current_items_without_mutating_running_usage():
    cm = manager.ContextManager.__new__(manager.ContextManager)
    cm.items = [
        Message(role="system", content="system"),
        Message(role="user", content="hello world"),
    ]
    cm.running_context_usage = 7

    with patch("litellm.token_counter", return_value=12_345):
        assert cm.estimate_usage("openai/gpt-5.5") == 12_345

    assert cm.running_context_usage == 7


def test_domain_pack_none_injects_research_only_context(monkeypatch):
    monkeypatch.setattr(manager, "_get_hf_username", lambda _token=None: "unknown")

    cm = manager.ContextManager(
        model_max_tokens=65_536,
        tool_specs=[],
        hf_token=None,
        local_mode=True,
        domain_pack="none",
    )

    assert "Research-only mode" in cm.system_prompt
    assert "The active domain pack is `none`" in cm.system_prompt
