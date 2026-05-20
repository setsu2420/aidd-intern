"""Regression tests for interactive CLI rendering and research model routing."""

import asyncio
import json
import subprocess
import sys
from io import StringIO
from types import SimpleNamespace

import pytest
from rich.console import Console

import agent.main as main_mod
from agent.tools.research_tool import _get_research_model
from agent.utils import terminal_display


def test_direct_anthropic_research_model_stays_off_bedrock():
    assert (
        _get_research_model("anthropic/claude-opus-4-6")
        == "anthropic/claude-sonnet-4-6"
    )


def test_bedrock_anthropic_research_model_stays_on_bedrock():
    assert (
        _get_research_model("bedrock/us.anthropic.claude-opus-4-6-v1")
        == "bedrock/us.anthropic.claude-sonnet-4-6"
    )


def test_non_anthropic_research_model_is_unchanged():
    assert _get_research_model("openai/gpt-5.4") == "openai/gpt-5.4"


def test_help_output_keeps_descriptions_aligned(monkeypatch):
    output = StringIO()
    console = Console(
        file=output,
        color_system=None,
        theme=terminal_display._THEME,
        width=120,
    )
    monkeypatch.setattr(terminal_display, "_console", console)

    terminal_display.print_help()

    lines = [line.rstrip() for line in output.getvalue().splitlines() if line.strip()]
    description_columns = []
    for command, args, description in terminal_display.HELP_ROWS:
        line = next(line for line in lines if command in line)
        if args:
            assert args in line
        description_columns.append(line.index(description))

    assert len(set(description_columns)) == 1


def test_help_output_recomputes_widths_from_rows():
    rows = terminal_display.HELP_ROWS + (
        ("/longer-command", "[longer-args]", "Synthetic help row"),
    )
    output = StringIO()
    Console(
        file=output,
        color_system=None,
        theme=terminal_display._THEME,
        width=140,
    ).print(terminal_display.format_help_text(rows))

    lines = [line.rstrip() for line in output.getvalue().splitlines() if line.strip()]
    description_columns = [
        next(line for line in lines if command in line).index(description)
        for command, _args, description in rows
    ]

    assert len(set(description_columns)) == 1


def test_context_status_formats_live_usage():
    class FakeContext:
        def __init__(self):
            self.items = [object(), object()]
            self.model_max_tokens = 65_536
            self.compaction_threshold = 58_982

        def estimate_usage(self, model_name: str) -> int:
            assert model_name == "openai/gpt-5.5"
            return 12_345

    session = SimpleNamespace(
        context_manager=FakeContext(),
        config=SimpleNamespace(model_name="openai/gpt-5.5"),
        turn_count=3,
    )

    assert (
        terminal_display.format_context_status(
            session, include_turns=True, include_items=True
        )
        == "Context [##----------] 12.3k / 65.5k (18.8%) | compact @ 59.0k | turns 3 | items 2"
    )


def test_banner_defers_command_hint_until_ready(monkeypatch):
    output = StringIO()
    console = Console(
        file=output,
        color_system=None,
        theme=terminal_display._THEME,
        width=120,
    )
    monkeypatch.setattr(terminal_display, "_console", console)
    monkeypatch.delenv("AIDD_INTERN_BOOT_ANIMATION", raising=False)

    terminal_display.print_banner(
        model="siliconflow/deepseek-ai/DeepSeek-V4-Flash",
        hf_user=None,
        tool_runtime="local filesystem",
    )
    terminal_display.print_init_done(tool_count=23)

    rendered = output.getvalue()
    assert rendered.count("/help for commands") == 1
    assert "Tools: loading..." in rendered
    assert "Tools: 23 loaded" in rendered


@pytest.mark.asyncio
async def test_get_user_input_attaches_context_toolbar(monkeypatch):
    class FakeContext:
        def __init__(self):
            self.items = [object(), object()]
            self.model_max_tokens = 65_536
            self.compaction_threshold = 58_982

        def estimate_usage(self, model_name: str) -> int:
            assert model_name == "openai/gpt-5.5"
            return 12_345

    captured = {}

    class FakePromptSession:
        async def prompt_async(self, message, **kwargs):
            captured["message"] = message
            captured["kwargs"] = kwargs
            return "hello"

    session = SimpleNamespace(
        context_manager=FakeContext(),
        config=SimpleNamespace(model_name="openai/gpt-5.5"),
        turn_count=3,
    )

    result = await main_mod.get_user_input(FakePromptSession(), session=session)

    assert result == "hello"
    assert captured["kwargs"][
        "bottom_toolbar"
    ] == terminal_display.format_context_status(session)


def test_subagent_display_does_not_spawn_background_redraw(monkeypatch):
    calls: list[object] = []

    def _unexpected_future(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("background redraw task should not be created")

    monkeypatch.setattr("asyncio.ensure_future", _unexpected_future)
    monkeypatch.setattr(
        terminal_display,
        "_console",
        SimpleNamespace(file=StringIO(), width=100),
    )

    mgr = terminal_display.SubAgentDisplayManager()
    mgr.start("agent-1", "research")
    mgr.add_call("agent-1", '▸ hf_papers  {"operation": "search"}')
    mgr.clear("agent-1")

    assert calls == []


def test_cli_forwards_model_flag_to_interactive_main(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_main(*, model=None, sandbox_tools=False):
        seen["model"] = model
        seen["sandbox_tools"] = sandbox_tools

    monkeypatch.setattr(sys, "argv", ["aidd-intern", "--model", "openai/gpt-5.5"])
    monkeypatch.setattr(main_mod, "main", fake_main)

    main_mod.cli()

    assert seen == {
        "model": "openai/gpt-5.5",
        "sandbox_tools": False,
    }


def test_cli_forwards_sandbox_flag_to_interactive_main(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_main(*, model=None, sandbox_tools=False):
        seen["model"] = model
        seen["sandbox_tools"] = sandbox_tools

    monkeypatch.setattr(sys, "argv", ["aidd-intern", "--sandbox-tools"])
    monkeypatch.setattr(main_mod, "main", fake_main)

    main_mod.cli()

    assert seen == {"model": None, "sandbox_tools": True}


@pytest.mark.asyncio
async def test_model_command_global_saves_catalog_default(monkeypatch, tmp_path):
    models_path = tmp_path / "models.json"
    models_path.write_text(
        json.dumps(
            {
                "default": "openrouter/openai/gpt-5.2",
                "models": [
                    {
                        "id": "siliconflow/deepseek-ai/DeepSeek-V4-Flash",
                        "label": "DeepSeek Flash",
                        "aliases": ["flash"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    class Config:
        model_name = "openrouter/openai/gpt-5.2"
        models_config = str(models_path)
        reasoning_effort = None

    class Session:
        model_effective_effort = {}

        def update_model(self, model_id):
            Config.model_name = model_id

    async def fake_probe(model_id, config, session, console, hf_token):
        session.update_model(model_id)

    from agent.core import model_switcher

    monkeypatch.setattr(model_switcher, "probe_and_switch_model", fake_probe)
    monkeypatch.setattr("agent.core.hf_tokens.resolve_hf_token", lambda: None)

    result = await main_mod._handle_slash_command(
        "/model --global flash",
        Config,
        [Session()],
        asyncio.Queue(),
        [0],
    )

    assert result is None
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    assert payload["default"] == "siliconflow/deepseek-ai/DeepSeek-V4-Flash"


def test_cli_forwards_sandbox_flag_to_headless_main(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_headless_main(
        prompt,
        *,
        model=None,
        max_iterations=None,
        stream=True,
        sandbox_tools=False,
    ):
        seen.update(
            {
                "prompt": prompt,
                "model": model,
                "max_iterations": max_iterations,
                "stream": stream,
                "sandbox_tools": sandbox_tools,
            }
        )

    monkeypatch.setattr(
        sys,
        "argv",
        ["aidd-intern", "--sandbox-tools", "--no-stream", "train a model"],
    )
    monkeypatch.setattr(main_mod, "headless_main", fake_headless_main)

    main_mod.cli()

    assert seen == {
        "prompt": "train a model",
        "model": None,
        "max_iterations": None,
        "stream": False,
        "sandbox_tools": True,
    }


def test_cli_doctor_runs_real_diagnostic_without_starting_chat():
    print("STEP 1: Running the real CLI doctor command in a subprocess")
    result = subprocess.run(
        [sys.executable, "-m", "agent.main", "--doctor"],
        check=False,
        capture_output=True,
        text=True,
    )

    print(f"STEP 2: doctor exit code = {result.returncode}")
    assert result.returncode in {0, 1}

    print("STEP 3: Checking doctor output includes diagnostic steps")
    assert "STEP 1: Checking Python runtime" in result.stdout
    assert "STEP 6: Checking AIDD-Intern version" in result.stdout
    assert "Doctor summary:" in result.stdout
    assert "Result:" in result.stdout

    print("STEP 4: Checking chat UI startup text is absent")
    assert "--- Agent" not in result.stdout
    assert result.stderr == ""


@pytest.mark.asyncio
async def test_interactive_main_applies_model_override_before_banner(monkeypatch):
    class StopAfterBanner(Exception):
        pass

    def fake_banner(*, model=None, hf_user=None, tool_runtime=None):
        assert model == "openai/gpt-5.5"
        assert hf_user == "tester"
        assert tool_runtime == "local filesystem"
        raise StopAfterBanner

    monkeypatch.setattr(main_mod.os, "system", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(main_mod, "PromptSession", lambda: object())
    monkeypatch.setattr(main_mod, "resolve_hf_token", lambda: "hf-token")
    monkeypatch.setattr(
        main_mod, "_validated_hf_token", lambda token: (token, "tester")
    )
    monkeypatch.setattr(
        main_mod,
        "load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            model_name="moonshotai/Kimi-K2.6",
            mcpServers={},
            tool_runtime="local",
        ),
    )
    monkeypatch.setattr(main_mod, "print_banner", fake_banner)

    with pytest.raises(StopAfterBanner):
        await main_mod.main(model="openai/gpt-5.5")


@pytest.mark.asyncio
async def test_local_model_local_runtime_skips_hf_token_prompt(monkeypatch):
    class StopAfterBanner(Exception):
        pass

    async def fail_prompt(_prompt_session):
        raise AssertionError("local model with local tools should not prompt")

    def fake_banner(*, model=None, hf_user=None, tool_runtime=None):
        assert model == "llamacpp/model"
        assert hf_user is None
        assert tool_runtime == "local filesystem"
        raise StopAfterBanner

    monkeypatch.setattr(main_mod.os, "system", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(main_mod, "PromptSession", lambda: object())
    monkeypatch.setattr(main_mod, "resolve_hf_token", lambda: None)
    monkeypatch.setattr(main_mod, "_prompt_and_save_hf_token", fail_prompt)
    monkeypatch.setattr(main_mod, "_validated_hf_token", lambda _token: (None, None))
    monkeypatch.setattr(
        main_mod,
        "load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            model_name="llamacpp/model",
            mcpServers={},
            tool_runtime="local",
        ),
    )
    monkeypatch.setattr(main_mod, "print_banner", fake_banner)

    with pytest.raises(StopAfterBanner):
        await main_mod.main()


@pytest.mark.asyncio
async def test_local_model_local_runtime_drops_invalid_hf_token_for_mcp(monkeypatch):
    class StopAfterToolRouter(Exception):
        pass

    seen: dict[str, object] = {}

    class FakeGateway:
        def __init__(self, _config):
            pass

        async def start(self):
            pass

    class FakeToolRouter:
        def __init__(self, mcp_servers, *, hf_token=None, local_mode=True):
            seen["mcp_servers"] = mcp_servers
            seen["hf_token"] = hf_token
            seen["local_mode"] = local_mode
            raise StopAfterToolRouter

    from agent.core import hf_router_catalog

    monkeypatch.setattr(main_mod.os, "system", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(main_mod, "PromptSession", lambda: object())
    monkeypatch.setattr(main_mod, "resolve_hf_token", lambda: "stale-token")
    monkeypatch.setattr(main_mod, "_validated_hf_token", lambda _token: (None, None))
    monkeypatch.setattr(main_mod, "print_banner", lambda **_kwargs: None)
    monkeypatch.setattr(hf_router_catalog, "prewarm", lambda: None)
    monkeypatch.setattr(
        main_mod,
        "load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            model_name="vllm/qwen3.6-35b-a3b",
            mcpServers={"hf-mcp-server": object()},
            messaging=SimpleNamespace(default_auto_destinations=lambda: []),
            tool_runtime="local",
        ),
    )
    monkeypatch.setattr(main_mod, "NotificationGateway", FakeGateway)
    monkeypatch.setattr(main_mod, "ToolRouter", FakeToolRouter)

    with pytest.raises(StopAfterToolRouter):
        await main_mod.main()

    assert seen["hf_token"] is None
    assert seen["local_mode"] is True


@pytest.mark.asyncio
async def test_local_model_sandbox_runtime_prompts_for_hf_token(monkeypatch):
    class StopAfterBanner(Exception):
        pass

    prompted = False

    async def fake_prompt(_prompt_session):
        nonlocal prompted
        prompted = True
        return "hf-token"

    def fake_banner(*, model=None, hf_user=None, tool_runtime=None):
        assert model == "llamacpp/model"
        assert hf_user == "tester"
        assert tool_runtime == "HF sandbox"
        raise StopAfterBanner

    monkeypatch.setattr(main_mod.os, "system", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(main_mod, "PromptSession", lambda: object())
    monkeypatch.setattr(main_mod, "resolve_hf_token", lambda: None)
    monkeypatch.setattr(main_mod, "_prompt_and_save_hf_token", fake_prompt)
    monkeypatch.setattr(
        main_mod, "_validated_hf_token", lambda token: (token, "tester")
    )
    monkeypatch.setattr(
        main_mod,
        "load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            model_name="llamacpp/model",
            mcpServers={},
            tool_runtime="local",
        ),
    )
    monkeypatch.setattr(main_mod, "print_banner", fake_banner)

    with pytest.raises(StopAfterBanner):
        await main_mod.main(sandbox_tools=True)

    assert prompted is True


@pytest.mark.asyncio
async def test_interactive_main_passes_sandbox_runtime_to_tool_router(monkeypatch):
    class StopAfterToolRouter(Exception):
        pass

    seen: dict[str, object] = {}

    class FakeGateway:
        def __init__(self, _config):
            pass

        async def start(self):
            pass

    class FakeToolRouter:
        def __init__(self, mcp_servers, *, hf_token=None, local_mode=True):
            seen["mcp_servers"] = mcp_servers
            seen["hf_token"] = hf_token
            seen["local_mode"] = local_mode
            raise StopAfterToolRouter

    from agent.core import hf_router_catalog

    monkeypatch.setattr(main_mod.os, "system", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(main_mod, "PromptSession", lambda: object())
    monkeypatch.setattr(main_mod, "resolve_hf_token", lambda: "hf-token")
    monkeypatch.setattr(
        main_mod, "_validated_hf_token", lambda token: (token, "tester")
    )
    monkeypatch.setattr(main_mod, "print_banner", lambda **_kwargs: None)
    monkeypatch.setattr(hf_router_catalog, "prewarm", lambda: None)
    monkeypatch.setattr(
        main_mod,
        "load_config",
        lambda _path, **_kwargs: SimpleNamespace(
            model_name="llamacpp/model",
            mcpServers={"server": object()},
            messaging=SimpleNamespace(default_auto_destinations=lambda: []),
            tool_runtime="local",
        ),
    )
    monkeypatch.setattr(main_mod, "NotificationGateway", FakeGateway)
    monkeypatch.setattr(main_mod, "ToolRouter", FakeToolRouter)

    with pytest.raises(StopAfterToolRouter):
        await main_mod.main(sandbox_tools=True)

    assert seen["hf_token"] == "hf-token"
    assert seen["local_mode"] is False


@pytest.mark.asyncio
async def test_initial_sandbox_preload_waits_before_prompt():
    waited = False

    async def preload():
        nonlocal waited
        await asyncio.sleep(0)
        waited = True

    task = asyncio.create_task(preload())
    await main_mod._wait_for_initial_sandbox_preload(
        [SimpleNamespace(sandbox_preload_task=task)]
    )

    assert waited is True
