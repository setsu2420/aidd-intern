"""Regression tests for the 2026-05-03 infinite-compaction-loop bug.

Pod logs from prod-114 showed sessions stuck retrying compaction every
few seconds because a single oversized tool output in the untouched tail
kept the post-compact context above the 90% threshold:

    Context compacted: 200001 -> 215566 tokens
    Context compacted: 215566 -> 215572 tokens
    ContextWindowExceededError — forcing compaction
    ... (continues for 5+ minutes)

These tests cover three fixes:

1. ``_truncate_oversized`` replaces oversized message content with a
   placeholder and preserves all extended-thinking metadata fields.
2. ``compact()`` raises ``CompactionFailedError`` when the post-compact
   context is still over threshold.
3. ``_compact_and_notify`` catches the error, sets ``session.is_running
   = False``, and emits a ``session_terminated`` event so callers can
   exit the agent loop.

The P0 caught by PR #213 review (loop didn't actually exit on
``is_running = False``) would have been caught by an end-to-end
behavioral test of #3 — that gap is closed by the
``test_compact_and_notify_terminates_session`` case below.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import Message

from agent.context_manager.manager import (
    CompactionFailedError,
    ContextManager,
    _MAX_TOKENS_PER_MESSAGE,
    context_policy_for_window,
)
from agent.core.agent_loop import Handlers


# ── helpers ────────────────────────────────────────────────────────────


def _make_cm(
    *,
    model_max_tokens: int = 100_000,
    compact_size: int = 1_000,
    untouched_messages: int = 5,
) -> ContextManager:
    cm = ContextManager.__new__(ContextManager)
    cm.system_prompt = "system"
    cm.model_max_tokens = model_max_tokens
    cm.compact_size = compact_size
    cm.running_context_usage = 0
    cm.untouched_messages = untouched_messages
    cm.items = [Message(role="system", content="system")]
    cm.on_message_added = None
    return cm


def _msg(role: str, content: str | None = "x", **extra) -> Message:
    return Message(role=role, content=content, **extra)


def test_context_policy_for_65k_models_compacts_early():
    policy = context_policy_for_window(65_536)

    assert policy["threshold_ratio"] < 0.75
    assert policy["compact_size"] <= 1500
    assert policy["untouched_messages"] == 3
    assert policy["max_tokens_per_message"] < _MAX_TOKENS_PER_MESSAGE


# ── _truncate_oversized ────────────────────────────────────────────────


def test_truncate_oversized_skips_messages_below_threshold():
    cm = _make_cm()
    msgs = [_msg("user", "small content")]
    with patch("litellm.token_counter", return_value=100):
        out = cm._truncate_oversized(msgs, "anthropic/claude-opus-4-6")
    assert out == msgs  # unchanged


def test_truncate_oversized_replaces_content_above_threshold():
    cm = _make_cm()
    big = "x" * (_MAX_TOKENS_PER_MESSAGE * 5)
    msgs = [_msg("user", big)]
    # token_counter returns the simulated big size for any message in this test
    with patch("litellm.token_counter", return_value=_MAX_TOKENS_PER_MESSAGE * 2):
        out = cm._truncate_oversized(msgs, "anthropic/claude-opus-4-6")
    assert len(out) == 1
    assert out[0].content != big
    assert "[truncated for compaction" in out[0].content
    assert str(_MAX_TOKENS_PER_MESSAGE * 2) in out[0].content


def test_truncate_oversized_preserves_thinking_blocks():
    """Anthropic extended-thinking models reject the next request with
    ``Invalid signature in thinking block`` if a prior assistant message
    drops thinking_blocks. Truncation must keep this metadata.
    """
    cm = _make_cm()
    big = "x" * (_MAX_TOKENS_PER_MESSAGE * 5)
    thinking = [{"type": "thinking", "thinking": "...", "signature": "abc123"}]
    msg = Message(role="assistant", content=big)
    msg.thinking_blocks = thinking
    msg.reasoning_content = "deep thought"
    with patch("litellm.token_counter", return_value=_MAX_TOKENS_PER_MESSAGE * 2):
        out = cm._truncate_oversized([msg], "anthropic/claude-opus-4-6")
    assert getattr(out[0], "thinking_blocks", None) == thinking
    assert getattr(out[0], "reasoning_content", None) == "deep thought"


def test_truncate_oversized_never_touches_system_message():
    """The system prompt is the agent's instructions — must never be truncated.

    Caught by the integration smoke test on PR #213: when items has fewer than
    ``untouched_messages`` entries, the slice math in ``compact()`` can let
    ``items[0]`` (the system message) leak into the ``recent_messages`` list
    that gets passed to ``_truncate_oversized``. The function must guard
    explicitly against this.
    """
    cm = _make_cm()
    huge_system = "x" * (_MAX_TOKENS_PER_MESSAGE * 5)
    msgs = [_msg("system", huge_system)]
    with patch("litellm.token_counter", return_value=_MAX_TOKENS_PER_MESSAGE * 2):
        out = cm._truncate_oversized(msgs, "anthropic/claude-opus-4-6")
    assert out[0].content == huge_system, "system message must never be truncated"


def test_truncate_oversized_resilient_to_token_counter_failure():
    """token_counter occasionally raises on edge-case content. A blip there
    must NOT drop the message — better to leave it and let compaction
    handle it (or fail with CompactionFailedError) than to lose data.
    """
    cm = _make_cm()
    msgs = [_msg("user", "anything")]
    with patch("litellm.token_counter", side_effect=Exception("counter blew up")):
        out = cm._truncate_oversized(msgs, "anthropic/claude-opus-4-6")
    assert out == msgs


# ── compact() raises CompactionFailedError ─────────────────────────────


@pytest.mark.asyncio
async def test_compact_raises_when_post_compact_still_over_threshold():
    """The whole point of the new behavior: don't loop on a useless
    compaction call. Raise so the caller can terminate the session.
    """
    cm = _make_cm(model_max_tokens=100_000)
    # Build a context that's "over threshold" from the start
    cm.items = [
        Message(role="system", content="system"),
        Message(role="user", content="task"),
        Message(role="assistant", content="x" * 1000),
        Message(role="user", content="follow-up 1"),
        Message(role="assistant", content="reply 1"),
        Message(role="user", content="follow-up 2"),
        Message(role="assistant", content="reply 2"),
    ]
    cm.running_context_usage = 95_000  # over threshold (90% of 100k = 90k)

    # Mock summarize_messages to return a tiny summary; mock _recompute_usage
    # to keep the running_context_usage above threshold so compact() raises.
    async def fake_summarize(*args, **kwargs):
        return ("summary", 10)

    def fake_recompute(self, model_name):
        # Simulate post-compact still over threshold
        self.running_context_usage = 95_000

    with (
        patch(
            "agent.context_manager.manager.summarize_messages",
            side_effect=fake_summarize,
        ),
        patch.object(ContextManager, "_recompute_usage", fake_recompute),
        # Avoid token_counter calls in _truncate_oversized
        patch("litellm.token_counter", return_value=100),
    ):
        with pytest.raises(CompactionFailedError):
            await cm.compact(
                model_name="anthropic/claude-opus-4-6",
                tool_specs=None,
                hf_token=None,
                session=None,
            )


@pytest.mark.asyncio
async def test_compact_does_not_duplicate_system_when_idx_is_zero():
    """Regression for the second P0 caught by bot review on PR #213.

    When ``len(items) == untouched_messages`` (the canonical 5-message
    early-compaction case: system + user-task + giant-tool-output +
    user-followup + assistant-reply), ``idx`` initialises to 0 and the
    walk-back ``while idx > 1`` loop is a no-op. Without an explicit
    clamp ``if idx < 1: idx = 1``, ``recent_messages = items[0:]``
    starts at the system message, and the rebuild duplicates system +
    first-user. Anthropic API rejects two system messages.
    """
    cm = _make_cm(model_max_tokens=100_000, untouched_messages=5)
    cm.items = [
        Message(role="system", content="system"),
        Message(role="user", content="task"),
        Message(role="assistant", content="ok"),  # would be the only
        # message_to_summarize but the
        # idx bug pulls it into recent
        Message(role="user", content="followup"),
        Message(role="assistant", content="reply"),
    ]  # exactly 5 = untouched_messages, so idx initialises to 0
    cm.running_context_usage = 95_000

    async def fake_summarize(*args, **kwargs):
        return ("summary", 10)

    def fake_recompute(self, model_name):
        self.running_context_usage = 5_000

    with (
        patch(
            "agent.context_manager.manager.summarize_messages",
            side_effect=fake_summarize,
        ),
        patch.object(ContextManager, "_recompute_usage", fake_recompute),
        patch("litellm.token_counter", return_value=100),
    ):
        await cm.compact(
            model_name="anthropic/claude-opus-4-6",
            tool_specs=None,
            hf_token=None,
            session=None,
        )

    # Critical assertion: only ONE system message in items
    system_count = sum(1 for m in cm.items if m.role == "system")
    assert system_count == 1, (
        f"Expected exactly 1 system message, found {system_count}. "
        f"Roles: {[m.role for m in cm.items]}"
    )
    # And the first-user "task" message must also appear exactly once.
    # Bot review on PR #213 caught a follow-up bug: clamping idx=1
    # excludes the system but still overlaps with first_user_idx (also 1),
    # so first_user_msg ends up in BOTH head and recent_messages →
    # duplicate user message → Anthropic 400 (two consecutive user roles).
    task_count = sum(
        1 for m in cm.items if m.role == "user" and (m.content or "") == "task"
    )
    assert task_count == 1, (
        f"Expected exactly 1 'task' user message, found {task_count}. "
        f"Roles+content: {[(m.role, (m.content or '')[:20]) for m in cm.items]}"
    )
    # Defense in depth: no two consecutive same-role messages (Anthropic
    # API contract). System counts separately.
    non_system = [m for m in cm.items if m.role != "system"]
    for i in range(1, len(non_system)):
        assert non_system[i].role != non_system[i - 1].role, (
            f"Two consecutive {non_system[i].role} messages at non-system "
            f"position {i - 1},{i} — Anthropic API rejects this. "
            f"Roles: {[m.role for m in cm.items]}"
        )


@pytest.mark.asyncio
async def test_compact_succeeds_when_post_compact_under_threshold():
    """Happy path: when compaction does its job, no exception raised."""
    cm = _make_cm(model_max_tokens=100_000)
    cm.items = [
        Message(role="system", content="system"),
        Message(role="user", content="task"),
        Message(role="assistant", content="x" * 1000),
        Message(role="user", content="follow-up"),
        Message(role="assistant", content="reply"),
        Message(role="user", content="follow-up 2"),
        Message(role="assistant", content="reply 2"),
    ]
    cm.running_context_usage = 95_000

    async def fake_summarize(*args, **kwargs):
        return ("summary", 10)

    def fake_recompute(self, model_name):
        self.running_context_usage = 5_000  # well under threshold

    with (
        patch(
            "agent.context_manager.manager.summarize_messages",
            side_effect=fake_summarize,
        ),
        patch.object(ContextManager, "_recompute_usage", fake_recompute),
        patch("litellm.token_counter", return_value=100),
    ):
        await cm.compact(
            model_name="anthropic/claude-opus-4-6",
            tool_specs=None,
            hf_token=None,
            session=None,
        )
    assert cm.running_context_usage == 5_000


# ── _compact_and_notify behavior on CompactionFailedError ──────────────


@pytest.mark.asyncio
async def test_compact_and_notify_terminates_session_on_failure():
    """The PR's #213's P0 bug-class: setting ``is_running = False`` is
    only effective if the agent loop checks it. This test asserts the
    flag IS set AND a ``session_terminated`` event is emitted, so a
    follow-up assertion in the agent loop test catches the loop-exit.
    """
    from agent.core.agent_loop import _compact_and_notify

    session = MagicMock()
    session.session_id = "sess-123"
    session.is_running = True
    session.config.model_name = "anthropic/claude-opus-4-6"
    session.hf_token = None
    session.tool_router.get_tool_specs_for_llm.return_value = []
    session.send_event = AsyncMock()

    cm = MagicMock()
    cm.running_context_usage = 95_000
    cm.compaction_threshold = 90_000
    cm.model_max_tokens = 100_000
    cm.items = []
    cm.needs_compaction = True
    cm.compact = AsyncMock(side_effect=CompactionFailedError("ineffective"))
    session.context_manager = cm

    await _compact_and_notify(session)

    assert session.is_running is False, (
        "_compact_and_notify must set is_running=False so the agent loop "
        "can exit. P0 caught by bot review on PR #213 was that the loop "
        "didn't actually check this flag."
    )
    assert session.send_event.await_count == 1
    event = session.send_event.await_args.args[0]
    assert event.event_type == "session_terminated"
    assert event.data["reason"] == "compaction_failed"
    assert event.data["context_usage"] == 95_000


@pytest.mark.asyncio
async def test_compact_and_notify_passes_through_on_success():
    """When compaction succeeds, no termination event, is_running stays True."""
    from agent.core.agent_loop import _compact_and_notify

    session = MagicMock()
    session.session_id = "sess-456"
    session.is_running = True
    session.config.model_name = "anthropic/claude-opus-4-6"
    session.hf_token = None
    session.tool_router.get_tool_specs_for_llm.return_value = []
    session.send_event = AsyncMock()

    cm = MagicMock()
    cm.running_context_usage = 5_000
    cm.compaction_threshold = 90_000
    cm.model_max_tokens = 100_000
    cm.items = []
    cm.needs_compaction = False
    cm.compact = AsyncMock(return_value=None)  # success
    session.context_manager = cm

    # Pretend old_usage == new_usage so the "compacted" event is also skipped
    await _compact_and_notify(session)

    assert session.is_running is True
    # No session_terminated event emitted
    for call in session.send_event.await_args_list:
        ev = call.args[0]
        assert ev.event_type != "session_terminated"


@pytest.mark.asyncio
async def test_run_agent_reports_local_llm_connection_without_traceback(monkeypatch):
    """A refused local vLLM port is a configuration problem, not useful retry
    material. The user-facing event should name the endpoint and avoid internal
    LiteLLM traceback noise.
    """

    class Context:
        items: list[Message] = []
        running_context_usage = 0
        model_max_tokens = 65_536
        compaction_threshold = 44_564
        needs_compaction = False

        def add_message(self, message, token_count=0):
            self.items.append(message)

        def get_messages(self):
            return self.items

        async def compact(self, *args, **kwargs):
            return None

    events = []

    async def send_event(event):
        events.append(event)

    async def no_sleep(_seconds):
        raise AssertionError("local connection refusal should not retry")

    async def no_auto_save():
        return None

    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.setattr("agent.core.agent_loop._env_value", lambda _name: None)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    session = SimpleNamespace(
        reset_cancel=lambda: None,
        pending_approval=None,
        context_manager=Context(),
        send_event=send_event,
        is_cancelled=False,
        is_running=True,
        config=SimpleNamespace(
            model_name="vllm/qwen3.6-35b-a3b",
            max_iterations=1,
            reasoning_effort=None,
        ),
        tool_router=SimpleNamespace(get_tool_specs_for_llm=lambda: []),
        hf_token=None,
        stream=True,
        current_plan=[],
        effective_effort_for=lambda _model: None,
        increment_turn=lambda: None,
        auto_save_if_needed=no_auto_save,
    )

    await Handlers.run_agent(session, "hello")

    error_events = [event for event in events if event.event_type == "error"]
    assert len(error_events) == 1
    error = error_events[0].data["error"]
    assert "Local LLM is not reachable." in error
    assert "Model: vllm/qwen3.6-35b-a3b" in error
    assert "Endpoint: http://127.0.0.1:9/v1" in error
    assert "curl http://127.0.0.1:9/v1/models" in error
    assert "Traceback" not in error
    assert "litellm.InternalServerError" not in error

    assert not any(
        event.event_type == "tool_log"
        and "LLM connection error, retrying" in event.data.get("log", "")
        for event in events
    )


@pytest.mark.asyncio
async def test_run_agent_falls_back_to_siliconflow_when_local_llm_is_down(
    monkeypatch,
):
    """When a shell export pins the default to a dead local vLLM, a configured
    SiliconFlow key gives the CLI a usable remote fallback.
    """
    from agent.core import agent_loop

    class Context:
        def __init__(self):
            self.items: list[Message] = []
            self.running_context_usage = 0
            self.model_max_tokens = 65_536
            self.compaction_threshold = 44_564
            self.needs_compaction = False

        def add_message(self, message, token_count=0):
            self.items.append(message)

        def get_messages(self):
            return self.items

        def apply_context_policy(self, _model_max_tokens):
            return None

        async def compact(self, *args, **kwargs):
            return None

    class SessionStub:
        def __init__(self):
            self.pending_approval = None
            self.context_manager = Context()
            self.events = []
            self.is_running = True
            self.config = SimpleNamespace(
                model_name="vllm/qwen3.6-35b-a3b",
                max_iterations=1,
                reasoning_effort=None,
            )
            self.tool_router = SimpleNamespace(get_tool_specs_for_llm=lambda: [])
            self.hf_token = None
            self.stream = False
            self.current_plan = []
            self.model_effective_effort = {}

        def reset_cancel(self):
            return None

        @property
        def is_cancelled(self):
            return False

        def effective_effort_for(self, _model):
            return None

        def update_model(self, model_name):
            self.config.model_name = model_name

        def increment_turn(self):
            return None

        async def auto_save_if_needed(self):
            return None

        async def send_event(self, event):
            self.events.append(event)

    async def fake_non_streaming(session, _messages, _tools, llm_params):
        assert session.config.model_name == "siliconflow/deepseek-ai/DeepSeek-V4-Flash"
        assert llm_params["model"] == "openai/deepseek-ai/DeepSeek-V4-Flash"
        await session.send_event(
            agent_loop.Event(
                event_type="assistant_message",
                data={"content": "fallback ok"},
            )
        )
        return agent_loop.LLMResult(
            content="fallback ok",
            tool_calls_acc={},
            token_count=1,
            finish_reason="stop",
        )

    async def no_sleep(_seconds):
        raise AssertionError("local connection refusal should not retry")

    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "siliconflow-secret")
    monkeypatch.delenv("AIDD_INTERN_SILICONFLOW_FALLBACK_MODEL", raising=False)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    monkeypatch.setattr(agent_loop, "_call_llm_non_streaming", fake_non_streaming)

    session = SessionStub()
    await Handlers.run_agent(session, "hello")

    assert session.config.model_name == "siliconflow/deepseek-ai/DeepSeek-V4-Flash"
    assert any(
        event.event_type == "tool_log"
        and "using siliconflow/deepseek-ai/DeepSeek-V4-Flash" in event.data["log"]
        for event in session.events
    )
    assert any(
        event.event_type == "assistant_message"
        and event.data["content"] == "fallback ok"
        for event in session.events
    )


@pytest.mark.asyncio
async def test_run_agent_falls_back_when_litellm_reports_local_connection_error(
    monkeypatch,
):
    """Defense in depth for cases where the preflight misses a local endpoint
    failure and the wrapped LiteLLM call reports it instead.
    """
    from agent.core import agent_loop

    class Context:
        def __init__(self):
            self.items: list[Message] = []
            self.running_context_usage = 0
            self.model_max_tokens = 65_536
            self.compaction_threshold = 44_564
            self.needs_compaction = False

        def add_message(self, message, token_count=0):
            self.items.append(message)

        def get_messages(self):
            return self.items

        def apply_context_policy(self, _model_max_tokens):
            return None

        async def compact(self, *args, **kwargs):
            return None

    class SessionStub:
        def __init__(self):
            self.pending_approval = None
            self.context_manager = Context()
            self.events = []
            self.is_running = True
            self.config = SimpleNamespace(
                model_name="vllm/qwen3.6-35b-a3b",
                max_iterations=1,
                reasoning_effort=None,
            )
            self.tool_router = SimpleNamespace(get_tool_specs_for_llm=lambda: [])
            self.hf_token = None
            self.stream = False
            self.current_plan = []
            self.model_effective_effort = {}

        def reset_cancel(self):
            return None

        @property
        def is_cancelled(self):
            return False

        def effective_effort_for(self, _model):
            return None

        def update_model(self, model_name):
            self.config.model_name = model_name

        def increment_turn(self):
            return None

        async def auto_save_if_needed(self):
            return None

        async def send_event(self, event):
            self.events.append(event)

    calls = []

    async def reachable_preflight(_model_name, _llm_params):
        return None

    async def fake_non_streaming(session, _messages, _tools, llm_params):
        calls.append(session.config.model_name)
        if session.config.model_name.startswith("vllm/"):
            raise agent_loop.LocalLLMConnectionError(
                model_name=session.config.model_name,
                api_base=llm_params["api_base"],
                detail="OpenAIException - Connection error.",
            )
        await session.send_event(
            agent_loop.Event(
                event_type="assistant_message",
                data={"content": "runtime fallback ok"},
            )
        )
        return agent_loop.LLMResult(
            content="runtime fallback ok",
            tool_calls_acc={},
            token_count=1,
            finish_reason="stop",
        )

    async def no_sleep(_seconds):
        raise AssertionError("local completion connection error should not retry")

    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:30000")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "siliconflow-secret")
    monkeypatch.setattr(agent_loop, "_ensure_local_llm_reachable", reachable_preflight)
    monkeypatch.setattr(agent_loop, "_call_llm_non_streaming", fake_non_streaming)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    session = SessionStub()
    await Handlers.run_agent(session, "hello")

    assert calls == [
        "vllm/qwen3.6-35b-a3b",
        "siliconflow/deepseek-ai/DeepSeek-V4-Flash",
    ]
    assert session.config.model_name == "siliconflow/deepseek-ai/DeepSeek-V4-Flash"
    assert any(
        event.event_type == "assistant_message"
        and event.data["content"] == "runtime fallback ok"
        for event in session.events
    )
