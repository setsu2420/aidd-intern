"""
Interactive CLI chat with the agent

Supports two modes:
  Interactive:  python -m agent.main
  Headless:     python -m agent.main "find me bird datasets"
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from prompt_toolkit.completion import Completer, Completion

from agent.core.approval_policy import is_scheduled_operation

CLI_CONFIG_PATH = Path(__file__).parent.parent / "configs" / "cli_agent_config.json"
logger = logging.getLogger(__name__)
PromptSession: Any | None = None
load_config: Any | None = None
resolve_hf_token: Any | None = None
submission_loop: Any | None = None
NotificationGateway: Any | None = None
ToolRouter: Any | None = None
print_banner: Any | None = None


def _configure_litellm_runtime() -> None:
    import litellm

    litellm.drop_params = True
    # Suppress the "Give Feedback / Get Help" banner LiteLLM prints to stderr
    # on every error — users don't need it, and our friendly errors cover it.
    litellm.suppress_debug_info = True


def _terminal_display():
    from agent.utils import terminal_display as td

    return td


def _get_load_config():
    loader = globals().get("load_config")
    if loader is not None:
        return loader

    from agent.config import load_config as loader

    globals()["load_config"] = loader
    return loader


def _get_resolve_hf_token():
    resolver = globals().get("resolve_hf_token")
    if resolver is not None:
        return resolver

    from agent.core.hf_tokens import resolve_hf_token as resolver

    globals()["resolve_hf_token"] = resolver
    return resolver


def _get_submission_loop():
    loop = globals().get("submission_loop")
    if loop is not None:
        return loop
    return None


def _load_submission_loop():
    loop = globals().get("submission_loop")
    if loop is not None:
        return loop

    from agent.core.agent_loop import submission_loop as loop

    globals()["submission_loop"] = loop
    return loop


def _get_notification_gateway_cls():
    gateway_cls = globals().get("NotificationGateway")
    if gateway_cls is not None:
        return gateway_cls

    from agent.messaging.gateway import NotificationGateway as gateway_cls

    globals()["NotificationGateway"] = gateway_cls
    return gateway_cls


def _get_tool_router_cls():
    router_cls = globals().get("ToolRouter")
    if router_cls is not None:
        return router_cls

    from agent.core.tools import ToolRouter as router_cls

    globals()["ToolRouter"] = router_cls
    return router_cls


def _get_print_banner():
    banner = globals().get("print_banner")
    if banner is not None:
        return banner

    banner = _terminal_display().print_banner
    globals()["print_banner"] = banner
    return banner


def _get_prompt_session_factory():
    factory = globals().get("PromptSession")
    if factory is not None:
        return factory

    from prompt_toolkit import PromptSession as prompt_session_factory

    globals()["PromptSession"] = prompt_session_factory
    return prompt_session_factory


def _apply_tool_runtime_override(config: Any, *, sandbox_tools: bool) -> str:
    if sandbox_tools:
        config.tool_runtime = "sandbox"
    return getattr(config, "tool_runtime", "local")


def _is_local_tool_runtime(config: Any) -> bool:
    return getattr(config, "tool_runtime", "local") == "local"


def _tool_runtime_label(local_mode: bool) -> str:
    return "local filesystem" if local_mode else "HF sandbox"


def _op_type(name: str) -> Any:
    from agent.core.session import OpType

    return getattr(OpType, name)


def _create_tool_router(
    mcp_servers: dict[str, Any],
    *,
    hf_token: str | None,
    local_mode: bool,
) -> Any:
    router_cls = _get_tool_router_cls()

    try:
        return router_cls(
            mcp_servers,
            hf_token=hf_token,
            local_mode=local_mode,
        )
    except TypeError as exc:
        if "local_mode" not in str(exc):
            raise
        return router_cls(
            mcp_servers,
            hf_token=hf_token,
        )


async def _wait_for_initial_sandbox_preload(session_holder: list | None) -> None:
    session = session_holder[0] if session_holder else None
    task = getattr(session, "sandbox_preload_task", None)
    if not task:
        return
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        raise
    except Exception:
        # The sandbox tool will surface the stored preload error on first use.
        return


def _is_scheduled_hf_job_tool(tool_info: dict[str, Any]) -> bool:
    if tool_info.get("tool") != "hf_jobs":
        return False
    arguments = tool_info.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return False
    if not isinstance(arguments, dict):
        return False
    return is_scheduled_operation(arguments.get("operation"))


def _configure_runtime_logging() -> None:
    """Keep third-party warning spam from punching through the interactive UI."""
    import logging

    logging.getLogger("LiteLLM").setLevel(logging.ERROR)
    logging.getLogger("litellm").setLevel(logging.ERROR)
    logging.getLogger("fastmcp").setLevel(logging.CRITICAL)
    logging.getLogger("mcp").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.ERROR)


def _safe_get_args(arguments: dict) -> dict:
    """Safely extract args dict from arguments, handling cases where LLM passes string."""
    args = arguments.get("args", {})
    # Sometimes LLM passes args as string instead of dict
    if isinstance(args, str):
        return {}
    return args if isinstance(args, dict) else {}


def _get_hf_user(token: str | None) -> str | None:
    """Resolve the HF username for a token, if available."""
    if not token:
        return None
    try:
        from huggingface_hub import HfApi

        return HfApi(token=token).whoami().get("name")
    except Exception:
        return None


def _validated_hf_token(token: str | None) -> tuple[str | None, str | None]:
    """Return (usable_token, username) after a lightweight HF token check."""
    if not token:
        return None, None
    try:
        from huggingface_hub import HfApi

        username = HfApi(token=token).whoami().get("name")
    except Exception:
        return None, None
    return token, username


async def _prompt_and_save_hf_token(prompt_session: Any) -> str:
    """Prompt user for HF token, validate it, save via huggingface_hub.login(). Loops until valid."""
    from prompt_toolkit.formatted_text import HTML
    from huggingface_hub import HfApi, login

    print("\nA Hugging Face token is required.")
    print("Get one at: https://huggingface.co/settings/tokens\n")

    while True:
        try:
            token = await prompt_session.prompt_async(
                HTML("<b>Paste your HF token: </b>")
            )
        except (EOFError, KeyboardInterrupt):
            print("\nToken is required to continue.")
            continue

        token = token.strip()
        if not token:
            print("Token cannot be empty.")
            continue

        # Validate token against the API
        try:
            api = HfApi(token=token)
            user_info = api.whoami()
            username = user_info.get("name", "unknown")
            print(f"Token valid (user: {username})")
        except Exception:
            print("Invalid token. Please try again.")
            continue

        # Save for future sessions
        try:
            login(token=token, add_to_git_credential=False)
            print("Token saved to ~/.cache/huggingface/token")
        except Exception as e:
            print(
                f"Warning: could not persist token ({e}), using for this session only."
            )

        return token


@dataclass
class Operation:
    """Operation to be executed by the agent"""

    op_type: Any
    data: Optional[dict[str, Any]] = None


@dataclass
class Submission:
    """Submission to the agent loop"""

    id: str
    operation: Operation


def _create_rich_console():
    """Get the shared rich Console."""
    return _terminal_display().get_console()


def _maybe_print_update_notice() -> None:
    if not sys.stdout.isatty():
        return
    try:
        from agent.core.version_check import check_for_update, format_update_notice

        notice = format_update_notice(check_for_update(CLI_CONFIG_PATH.parents[1]))
    except Exception:
        return
    if not notice:
        return
    console = _create_rich_console()
    console.print()
    console.print(f"[yellow]{notice}[/yellow]")
    console.print()


def _clear_terminal() -> None:
    command = ["cmd", "/c", "cls"] if os.name == "nt" else ["clear"]
    try:
        subprocess.run(command, check=False)
    except OSError:
        pass


class TUICompleter(Completer):
    """A premium context-aware TUI completer supporting commands, parameters and local path scan."""

    def __init__(self, config=None, session_holder=None):
        self.config = config
        self.session_holder = session_holder

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # 1. 以 '/' 开头，进行指令及参数补全
        if text.startswith("/"):
            commands = {
                "/help": "显示所有可用命令帮助信息",
                "/undo": "撤销上一步操作",
                "/compact": "强制对上下文进行紧凑压缩",
                "/new": "创建一个干净的新对话会话",
                "/clear": "清除会话内容并清空终端屏幕",
                "/resume": "从历史持久化会话中恢复",
                "/model": "切换或查询模型状态",
                "/yolo": "切换 YOLO 自动确认模式",
                "/effort": "设置模型推理努力级别 (reasoning effort)",
                "/status": "查看当前会话运行状态信息",
                "/usage": "查看本会话的 Token 和费用累计消耗",
                "/plan": "查看并管理当前活跃任务计划",
                "/theme": "查看或切换终端色彩主题",
                "/share-traces": "控制个人会话追踪数据集的公开可见性",
                "/hf-token": "动态查询或验证设置 Hugging Face Token",
            }

            parts = text.split()
            # 如果是 "/theme " 开头，联想主题
            if len(parts) >= 1 and parts[0] == "/theme":
                themes = ["sunset", "cyberpunk", "aurora", "monochrome", "ocean"]
                if text.startswith("/theme "):
                    theme_input = text[7:]
                    for t in themes:
                        if t.startswith(theme_input.lower()):
                            yield Completion(
                                t,
                                start_position=-len(theme_input),
                                display_meta="色彩主题",
                            )
                    return

            # 如果是 "/effort " 开头，联想 effort 级别
            if len(parts) >= 1 and parts[0] == "/effort":
                efforts = ["minimal", "low", "medium", "high", "xhigh", "max", "off"]
                if text.startswith("/effort "):
                    effort_input = text[8:]
                    for e in efforts:
                        if e.startswith(effort_input.lower()):
                            yield Completion(
                                e,
                                start_position=-len(effort_input),
                                display_meta="推理努力度",
                            )
                    return

            # 如果是 "/share-traces " 开头，联想 public/private
            if len(parts) >= 1 and parts[0] == "/share-traces":
                options = ["public", "private"]
                if text.startswith("/share-traces "):
                    trace_input = text[14:]
                    for o in options:
                        if o.startswith(trace_input.lower()):
                            yield Completion(
                                o,
                                start_position=-len(trace_input),
                                display_meta="数据集可见性",
                            )
                    return

            # 普通指令补全
            if len(parts) <= 1:
                cmd_input = parts[0] if parts else "/"
                for cmd, desc in commands.items():
                    if cmd.startswith(cmd_input.lower()):
                        yield Completion(
                            cmd, start_position=-len(cmd_input), display_meta=desc
                        )
                return

        # 2. 以 '@' 开头，进行本地文件和目录自动补全
        if "@" in text:
            last_at_idx = text.rfind("@")
            path_input = text[last_at_idx + 1 :]

            dir_part, file_part = os.path.split(path_input)
            search_dir = dir_part if dir_part else "."

            try:
                entries = os.listdir(search_dir)
                for entry in entries:
                    full_path = os.path.join(dir_part, entry) if dir_part else entry
                    if full_path.lower().startswith(path_input.lower()):
                        if (
                            entry.startswith(".")
                            and not entry.startswith("..")
                            and not path_input.startswith(".")
                        ):
                            continue

                        is_dir = os.path.isdir(os.path.join(search_dir, entry))
                        suffix = "/" if is_dir else ""
                        meta = "📁 目录" if is_dir else "📄 文件"

                        yield Completion(
                            full_path + suffix,
                            start_position=-len(path_input),
                            display_meta=meta,
                        )
            except Exception:
                pass
            return


class _ThinkingShimmer:
    """Animated shiny/shimmer thinking indicator — a bright gradient sweeps across the text with real-time metrics."""

    _BASE = (90, 90, 110)  # dim base color
    _WIDTH = 5  # shimmer width in characters
    _FPS = 24

    def __init__(self, console):
        self._console = console
        self._task = None
        self._running = False
        self._start_time = 0.0
        self._HIGHLIGHT = (255, 200, 80)

    def start(self):
        if self._running:
            return
        import time

        self._running = True
        self._start_time = time.monotonic()
        self._task = asyncio.ensure_future(self._animate())

    def stop(self):
        if not self._running:
            return  # no-op when never started (e.g. headless mode)
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        # Clear the shimmer line
        self._console.file.write("\r\033[K")
        self._console.file.flush()

    def _render_frame(self, text: str, offset: float) -> str:
        """Render one frame: a bright spot sweeps left-to-right across `text`."""
        out = []
        n = len(text)
        for i, ch in enumerate(text):
            # Distance from the shimmer center (wraps around)
            dist = abs(i - offset)
            wrap_dist = abs(i - offset + n + self._WIDTH)
            dist = min(dist, wrap_dist, abs(i - offset - n - self._WIDTH))
            # Blend factor: 1.0 at center, 0.0 beyond _WIDTH
            t = max(0.0, 1.0 - dist / self._WIDTH)
            t = t * t * (3 - 2 * t)  # smoothstep
            r = int(self._BASE[0] + (self._HIGHLIGHT[0] - self._BASE[0]) * t)
            g = int(self._BASE[1] + (self._HIGHLIGHT[1] - self._BASE[1]) * t)
            b = int(self._BASE[2] + (self._HIGHLIGHT[2] - self._BASE[2]) * t)
            out.append(f"\033[38;2;{r};{g};{b}m{ch}")
        out.append("\033[0m")
        return "".join(out)

    async def _animate(self):
        import time

        td = _terminal_display()
        active_theme = td._active_theme_name

        # 动态选取高亮色
        theme_highlights = {
            "sunset": (255, 167, 38),
            "cyberpunk": (255, 0, 127),
            "aurora": (0, 230, 118),
            "monochrome": (240, 240, 240),
            "ocean": (33, 150, 243),
        }
        self._HIGHLIGHT = theme_highlights.get(active_theme, (255, 200, 80))

        # 动态选取前缀呼吸 Emoji
        theme_emojis = {
            "sunset": "🧬 ",
            "cyberpunk": "⚡ ",
            "aurora": "🧪 ",
            "monochrome": "▪ ",
            "ocean": "🌊 ",
        }
        emoji = theme_emojis.get(active_theme, "🧬 ")

        speed = 0.45  # characters per frame
        pos = 0.0
        try:
            while self._running:
                elapsed = time.monotonic() - self._start_time
                text = f"Thinking ({elapsed:.1f}s)..."
                n = len(text)
                frame = self._render_frame(text, pos)
                self._console.file.write(f"\r  {emoji}{frame}")
                self._console.file.flush()
                pos = (pos + speed) % (n + self._WIDTH)
                await asyncio.sleep(1.0 / self._FPS)
        except asyncio.CancelledError:
            pass


class _StreamBuffer:
    """Accumulates streamed tokens, renders markdown block-by-block as complete
    blocks appear. A "block" is everything up to a paragraph break (\\n\\n).
    Unclosed code fences (odd count of ```) hold back flushing until closed so
    a code block is always rendered as one unit."""

    def __init__(self, console):
        self._console = console
        self._buffer = ""

    def add_chunk(self, text: str):
        self._buffer += text

    def _pop_block(self) -> str | None:
        """Extract the next complete block, or return None if nothing complete."""
        if self._buffer.count("```") % 2 == 1:
            return None  # inside an open code fence — wait for close
        idx = self._buffer.find("\n\n")
        if idx == -1:
            return None
        block = self._buffer[:idx]
        self._buffer = self._buffer[idx + 2 :]
        return block

    async def flush_ready(
        self,
        cancel_event: "asyncio.Event | None" = None,
        instant: bool = False,
    ):
        """Render any complete blocks that have accumulated; leave the tail."""
        td = _terminal_display()
        while True:
            if cancel_event is not None and cancel_event.is_set():
                return
            block = self._pop_block()
            if block is None:
                return
            if block.strip():
                await td.print_markdown(
                    block, cancel_event=cancel_event, instant=instant
                )

    async def finish(
        self,
        cancel_event: "asyncio.Event | None" = None,
        instant: bool = False,
    ):
        """Flush complete blocks, then render whatever incomplete tail remains."""
        td = _terminal_display()
        await self.flush_ready(cancel_event=cancel_event, instant=instant)
        if self._buffer.strip():
            await td.print_markdown(
                self._buffer, cancel_event=cancel_event, instant=instant
            )
        self._buffer = ""

    def discard(self):
        self._buffer = ""


async def event_listener(
    event_queue: asyncio.Queue,
    submission_queue: asyncio.Queue,
    turn_complete_event: asyncio.Event,
    ready_event: asyncio.Event,
    prompt_session: Any,
    config=None,
    session_holder=None,
) -> None:
    """Background task that listens for events and displays them"""
    td = _terminal_display()
    submission_id = [1000]
    last_tool_name = [None]
    console = _create_rich_console()
    shimmer = _ThinkingShimmer(console)
    stream_buf = _StreamBuffer(console)

    # Codex performance tracking metrics
    turn_metrics = {
        "start_time": 0.0,
        "llm_time_ms": 0,
        "tool_time_s": 0.0,
        "in_progress": False,
    }

    def _cancel_event():
        """Return the session's cancellation Event so print_markdown can abort
        its typewriter loop mid-stream when Ctrl+C fires."""
        s = session_holder[0] if session_holder else None
        return s._cancelled if s is not None else None

    while True:
        try:
            event = await event_queue.get()

            # Record turn start time on first activity
            if not turn_metrics["in_progress"] and event.event_type != "ready":
                import time

                turn_metrics["start_time"] = time.monotonic()
                turn_metrics["in_progress"] = True

            # Intercept telemetry data
            if event.event_type == "llm_call":
                latency = event.data.get("latency_ms", 0) if event.data else 0
                turn_metrics["llm_time_ms"] += latency

            if event.event_type == "ready":
                tool_count = event.data.get("tool_count", 0) if event.data else 0
                td.print_init_done(tool_count=tool_count)
                session = session_holder[0] if session_holder else None
                if session is not None:
                    td.print_context_status(session)
                ready_event.set()
            elif event.event_type == "assistant_message":
                shimmer.stop()
                content = event.data.get("content", "") if event.data else ""
                if content:
                    await td.print_markdown(content, cancel_event=_cancel_event())
            elif event.event_type == "assistant_chunk":
                content = event.data.get("content", "") if event.data else ""
                if content:
                    stream_buf.add_chunk(content)
                    # Flush any complete markdown blocks progressively so the
                    # user sees paragraphs appear as they're produced, not just
                    # at the end of the whole response.
                    shimmer.stop()
                    await stream_buf.flush_ready(cancel_event=_cancel_event())
            elif event.event_type == "assistant_stream_end":
                shimmer.stop()
                await stream_buf.finish(cancel_event=_cancel_event())
            elif event.event_type == "tool_call":
                shimmer.stop()
                stream_buf.discard()
                tool_name = event.data.get("tool", "") if event.data else ""
                arguments = event.data.get("arguments", {}) if event.data else {}
                if tool_name:
                    last_tool_name[0] = tool_name
                    # Skip printing research tool_call — the tool_log handler shows it
                    if tool_name != "research":
                        args_str = json.dumps(arguments)[:80]
                        td.print_tool_call(tool_name, args_str)
            elif event.event_type == "tool_output":
                output = event.data.get("output", "") if event.data else ""
                success = event.data.get("success", False) if event.data else False
                duration_s = event.data.get("duration_s", 0.0) if event.data else 0.0
                turn_metrics["tool_time_s"] += duration_s
                td.print_tool_duration(last_tool_name[0], success, duration_s)
                # Only show output for plan_tool — everything else is noise
                if last_tool_name[0] == "plan_tool" and output:
                    td.print_tool_output(
                        output, success, truncate=False, duration_s=0.0
                    )
                shimmer.start()
            elif event.event_type == "turn_complete":
                shimmer.stop()
                stream_buf.discard()
                td.print_turn_complete()

                # Performance metrics rendering
                import time

                elapsed = 0.0
                if turn_metrics["in_progress"]:
                    elapsed = time.monotonic() - turn_metrics["start_time"]
                llm_s = turn_metrics["llm_time_ms"] / 1000.0
                tool_s = turn_metrics["tool_time_s"]

                # Format turn metric block
                metrics_text = (
                    f"[bold rgb(255,200,80)]⏱ Turn Performance Metrics (Codex Style)[/bold rgb(255,200,80)]\n"
                    f"  • [bold cyan]Total Elapsed:[/bold cyan] {elapsed:.2f}s\n"
                    f"  • [bold cyan]Thinking (LLM):[/bold cyan] {llm_s:.2f}s\n"
                    f"  • [bold cyan]Tool Execution:[/bold cyan] {tool_s:.2f}s"
                )

                # Reset for next turn
                turn_metrics["in_progress"] = False
                turn_metrics["llm_time_ms"] = 0
                turn_metrics["tool_time_s"] = 0.0

                session = session_holder[0] if session_holder else None
                if session is not None:
                    td.print_context_status(session, include_turns=True)
                td.print_plan()

                # Print the metrics Panel beautifully
                from rich.panel import Panel

                console.print(
                    "  [dim]──────────────────────────────────────────────────[/dim]"
                )
                console.print(
                    Panel(
                        metrics_text,
                        border_style="dim rgb(255,200,80)",
                        expand=False,
                        padding=(0, 2),
                    )
                )
                console.print()

                if session is not None:
                    await session.send_deferred_turn_complete_notification(event)
                turn_complete_event.set()
            elif event.event_type == "interrupted":
                shimmer.stop()
                stream_buf.discard()
                td.print_interrupted()

                # Reset metrics on interrupt
                turn_metrics["in_progress"] = False
                turn_metrics["llm_time_ms"] = 0
                turn_metrics["tool_time_s"] = 0.0

                turn_complete_event.set()
            elif event.event_type == "undo_complete":
                console.print("[dim]Undone.[/dim]")
                turn_complete_event.set()
            elif event.event_type == "new_complete":
                data = event.data or {}
                if data.get("clear_screen"):
                    _clear_terminal()
                saved_path = data.get("saved_path")
                if saved_path:
                    console.print(
                        f"[dim]Started new chat. Prior chat saved to {saved_path}.[/dim]"
                    )
                else:
                    console.print("[dim]Started new chat.[/dim]")
                turn_complete_event.set()
            elif event.event_type == "resume_complete":
                data = event.data or {}
                path = data.get("path", "?")
                count = data.get("restored_count", 0)
                dropped = int(data.get("dropped_count", 0) or 0)
                model = data.get("model_name", "?")
                invalid_model = data.get("invalid_saved_model")
                forked = bool(data.get("forked", False))
                redacted = bool(data.get("had_redacted_content", False))
                verb = "Forked from" if forked else "Resumed"
                console.print(
                    f"[green]{verb}[/green] {path} "
                    f"([cyan]{count}[/cyan] messages, "
                    f"model [cyan]{model}[/cyan])."
                )
                if dropped:
                    console.print(
                        f"[yellow]Warning:[/yellow] dropped {dropped} "
                        "malformed message(s) while restoring — surrounding "
                        "tool-call alignment may be off."
                    )
                if invalid_model:
                    console.print(
                        f"[yellow]Warning:[/yellow] saved model id "
                        f"[cyan]{invalid_model}[/cyan] failed validation; "
                        f"kept current model [cyan]{model}[/cyan]."
                    )
                if forked:
                    console.print(
                        "[dim]Saved log belongs to a different user — kept "
                        "current session id; future saves go to a fresh file.[/dim]"
                    )
                if redacted:
                    console.print(
                        "[yellow]Note:[/yellow] tokens/secrets in restored "
                        "messages were scrubbed at save time. Your live tokens "
                        "are used for this session; [REDACTED_*] markers in "
                        "past messages are not re-injected."
                    )
                turn_complete_event.set()
            elif event.event_type == "tool_log":
                tool = event.data.get("tool", "") if event.data else ""
                log = event.data.get("log", "") if event.data else ""
                if log:
                    agent_id = event.data.get("agent_id", "") if event.data else ""
                    label = event.data.get("label", "") if event.data else ""
                    td.print_tool_log(tool, log, agent_id=agent_id, label=label)
            elif event.event_type == "tool_state_change":
                pass  # visual noise — approval flow handles this
            elif event.event_type == "error":
                shimmer.stop()
                stream_buf.discard()
                error = (
                    event.data.get("error", "Unknown error")
                    if event.data
                    else "Unknown error"
                )
                td.print_error(error)
                turn_complete_event.set()
            elif event.event_type == "shutdown":
                shimmer.stop()
                stream_buf.discard()
                break
            elif event.event_type == "processing":
                session = session_holder[0] if session_holder else None
                if session is not None:
                    td.print_context_status(
                        session, include_turns=True, include_items=True
                    )
                shimmer.start()
            elif event.event_type == "compacted":
                old_tokens = event.data.get("old_tokens", 0) if event.data else 0
                new_tokens = event.data.get("new_tokens", 0) if event.data else 0
                td.print_compacted(old_tokens, new_tokens)
                session = session_holder[0] if session_holder else None
                if session is not None:
                    td.print_context_status(session)
            elif event.event_type == "approval_required":
                # Handle batch approval format
                tools_data = event.data.get("tools", []) if event.data else []
                count = event.data.get("count", 0) if event.data else 0

                # If yolo mode is active, auto-approve everything except
                # scheduled HF jobs, whose recurring cost stays manual.
                if (
                    config
                    and config.yolo_mode
                    and not any(_is_scheduled_hf_job_tool(t) for t in tools_data)
                ):
                    approvals = [
                        {
                            "tool_call_id": t.get("tool_call_id", ""),
                            "approved": True,
                            "feedback": None,
                        }
                        for t in tools_data
                    ]
                    td.print_yolo_approve(count)
                    submission_id[0] += 1
                    approval_submission = Submission(
                        id=f"approval_{submission_id[0]}",
                        operation=Operation(
                            op_type=_op_type("EXEC_APPROVAL"),
                            data={"approvals": approvals},
                        ),
                    )
                    await submission_queue.put(approval_submission)
                    continue

                td.print_approval_header(count)
                approvals = []

                # Ask for approval for each tool
                for i, tool_info in enumerate(tools_data, 1):
                    tool_name = tool_info.get("tool", "")
                    arguments = tool_info.get("arguments", {})
                    tool_call_id = tool_info.get("tool_call_id", "")

                    # Handle case where arguments might be a JSON string
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            print(f"Warning: Failed to parse arguments for {tool_name}")
                            arguments = {}

                    operation = arguments.get("operation", "")

                    td.print_approval_item(i, count, tool_name, operation)

                    # Handle different tool types
                    if tool_name == "hf_jobs":
                        # Check if this is Python mode (script) or Docker mode (command)
                        script = arguments.get("script")
                        command = arguments.get("command")

                        if script:
                            from agent.utils.reliability_checks import (
                                check_training_script_save_pattern,
                            )

                            # Python mode
                            dependencies = arguments.get("dependencies", [])
                            python_version = arguments.get("python")
                            script_args = arguments.get("script_args", [])

                            # Show full script
                            print(f"Script:\n{script}")
                            if dependencies:
                                print(f"Dependencies: {', '.join(dependencies)}")
                            if python_version:
                                print(f"Python version: {python_version}")
                            if script_args:
                                print(f"Script args: {' '.join(script_args)}")

                            # Run reliability checks on the full script (not truncated)
                            check_message = check_training_script_save_pattern(script)
                            if check_message:
                                print(check_message)
                        elif command:
                            # Docker mode
                            image = arguments.get("image", "python:3.12")
                            command_str = (
                                " ".join(command)
                                if isinstance(command, list)
                                else str(command)
                            )
                            print(f"Docker image: {image}")
                            print(f"Command: {command_str}")

                        # Common parameters for jobs
                        hardware_flavor = arguments.get("hardware_flavor", "cpu-basic")
                        timeout = arguments.get("timeout", "30m")
                        env = arguments.get("env", {})
                        schedule = arguments.get("schedule")

                        print(f"Hardware: {hardware_flavor}")
                        print(f"Timeout: {timeout}")

                        if env:
                            env_keys = ", ".join(env.keys())
                            print(f"Environment variables: {env_keys}")

                        if schedule:
                            print(f"Schedule: {schedule}")

                    elif tool_name == "hf_private_repos":
                        # Handle private repo operations
                        args = _safe_get_args(arguments)

                        if operation in ["create_repo", "upload_file"]:
                            repo_id = args.get("repo_id", "")
                            repo_type = args.get("repo_type", "dataset")

                            # Build repo URL
                            type_path = "" if repo_type == "model" else f"{repo_type}s"
                            repo_url = (
                                f"https://huggingface.co/{type_path}/{repo_id}".replace(
                                    "//", "/"
                                )
                            )

                            print(f"Repository: {repo_id}")
                            print(f"Type: {repo_type}")
                            print("Private: Yes")
                            print(f"URL: {repo_url}")

                            # Show file preview for upload_file operation
                            if operation == "upload_file":
                                path_in_repo = args.get("path_in_repo", "")
                                file_content = args.get("file_content", "")
                                print(f"File: {path_in_repo}")

                                if isinstance(file_content, str):
                                    # Calculate metrics
                                    all_lines = file_content.split("\n")
                                    line_count = len(all_lines)
                                    size_bytes = len(file_content.encode("utf-8"))
                                    size_kb = size_bytes / 1024
                                    size_mb = size_kb / 1024

                                    print(f"Line count: {line_count}")
                                    if size_kb < 1024:
                                        print(f"Size: {size_kb:.2f} KB")
                                    else:
                                        print(f"Size: {size_mb:.2f} MB")

                                    # Show preview
                                    preview_lines = all_lines[:5]
                                    preview = "\n".join(preview_lines)
                                    print(
                                        f"Content preview (first 5 lines):\n{preview}"
                                    )
                                    if len(all_lines) > 5:
                                        print("...")

                    elif tool_name == "hf_repo_files":
                        # Handle repo files operations (upload, delete)
                        repo_id = arguments.get("repo_id", "")
                        repo_type = arguments.get("repo_type", "model")
                        revision = arguments.get("revision", "main")

                        # Build repo URL
                        if repo_type == "model":
                            repo_url = f"https://huggingface.co/{repo_id}"
                        else:
                            repo_url = f"https://huggingface.co/{repo_type}s/{repo_id}"

                        print(f"Repository: {repo_id}")
                        print(f"Type: {repo_type}")
                        print(f"Branch: {revision}")
                        print(f"URL: {repo_url}")

                        if operation == "upload":
                            path = arguments.get("path", "")
                            content = arguments.get("content", "")
                            create_pr = arguments.get("create_pr", False)

                            print(f"File: {path}")
                            if create_pr:
                                print("Mode: Create PR")

                            if isinstance(content, str):
                                all_lines = content.split("\n")
                                line_count = len(all_lines)
                                size_bytes = len(content.encode("utf-8"))
                                size_kb = size_bytes / 1024

                                print(f"Lines: {line_count}")
                                if size_kb < 1024:
                                    print(f"Size: {size_kb:.2f} KB")
                                else:
                                    print(f"Size: {size_kb / 1024:.2f} MB")

                                # Show full content
                                print(f"Content:\n{content}")

                        elif operation == "delete":
                            patterns = arguments.get("patterns", [])
                            if isinstance(patterns, str):
                                patterns = [patterns]
                            print(f"Patterns to delete: {', '.join(patterns)}")

                    elif tool_name == "hf_repo_git":
                        # Handle git operations (branches, tags, PRs, repo management)
                        repo_id = arguments.get("repo_id", "")
                        repo_type = arguments.get("repo_type", "model")

                        # Build repo URL
                        if repo_type == "model":
                            repo_url = f"https://huggingface.co/{repo_id}"
                        else:
                            repo_url = f"https://huggingface.co/{repo_type}s/{repo_id}"

                        print(f"Repository: {repo_id}")
                        print(f"Type: {repo_type}")
                        print(f"URL: {repo_url}")

                        if operation == "delete_branch":
                            branch = arguments.get("branch", "")
                            print(f"Branch to delete: {branch}")

                        elif operation == "delete_tag":
                            tag = arguments.get("tag", "")
                            print(f"Tag to delete: {tag}")

                        elif operation == "merge_pr":
                            pr_num = arguments.get("pr_num", "")
                            print(f"PR to merge: #{pr_num}")

                        elif operation == "create_repo":
                            private = arguments.get("private", False)
                            space_sdk = arguments.get("space_sdk")
                            print(f"Private: {private}")
                            if space_sdk:
                                print(f"Space SDK: {space_sdk}")

                        elif operation == "update_repo":
                            private = arguments.get("private")
                            gated = arguments.get("gated")
                            if private is not None:
                                print(f"Private: {private}")
                            if gated is not None:
                                print(f"Gated: {gated}")

                    # Get user decision for this item. Ctrl+C / EOF here is
                    # treated as "reject remaining" (matches Codex's modal
                    # priority and Forgecode's approval-cancel path). Without
                    # this, KeyboardInterrupt kills the event listener and
                    # the main loop deadlocks waiting for turn_complete.
                    try:
                        response = await prompt_session.prompt_async(
                            f"Approve item {i}? (y=yes, yolo=approve all, n=no, or provide feedback): "
                        )
                    except (KeyboardInterrupt, EOFError):
                        td.get_console().print(
                            "[dim]Approval cancelled — rejecting remaining items[/dim]"
                        )
                        approvals.append(
                            {
                                "tool_call_id": tool_call_id,
                                "approved": False,
                                "feedback": "User cancelled approval",
                            }
                        )
                        for remaining in tools_data[i:]:
                            approvals.append(
                                {
                                    "tool_call_id": remaining.get("tool_call_id", ""),
                                    "approved": False,
                                    "feedback": None,
                                }
                            )
                        break

                    response = response.strip().lower()

                    # Handle yolo mode activation
                    if response == "yolo":
                        config.yolo_mode = True
                        print(
                            "YOLO MODE ACTIVATED - Auto-approving all future tool calls"
                        )
                        # Auto-approve this item and all remaining
                        approvals.append(
                            {
                                "tool_call_id": tool_call_id,
                                "approved": True,
                                "feedback": None,
                            }
                        )
                        for remaining in tools_data[i:]:
                            approvals.append(
                                {
                                    "tool_call_id": remaining.get("tool_call_id", ""),
                                    "approved": True,
                                    "feedback": None,
                                }
                            )
                        break

                    approved = response in ["y", "yes"]
                    feedback = None if approved or response in ["n", "no"] else response

                    approvals.append(
                        {
                            "tool_call_id": tool_call_id,
                            "approved": approved,
                            "feedback": feedback,
                        }
                    )

                # Submit batch approval
                submission_id[0] += 1
                approval_submission = Submission(
                    id=f"approval_{submission_id[0]}",
                    operation=Operation(
                        op_type=_op_type("EXEC_APPROVAL"),
                        data={"approvals": approvals},
                    ),
                )
                await submission_queue.put(approval_submission)
                console.print()  # spacing after approval
            # Silently ignore other events

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Event listener error: {e}")


async def get_user_input(prompt_session: Any, session: Any | None = None) -> str:
    """Get user input asynchronously"""
    from prompt_toolkit.formatted_text import HTML

    td = _terminal_display()
    bottom_toolbar = td.format_context_status_html(session) if session else None

    theme_colors = {
        "sunset": "ansiyellow",
        "cyberpunk": "ansimagenta",
        "aurora": "ansigreen",
        "monochrome": "ansiwhite",
        "ocean": "ansiblue",
    }
    color = theme_colors.get(td._active_theme_name, "ansiyellow")

    prompt_str = f'\n<style fg="{color}"><b>🧬 intern</b></style> <b>❯</b> '
    return await prompt_session.prompt_async(
        HTML(prompt_str),
        bottom_toolbar=bottom_toolbar,
    )


async def _execute_local_shell_command(cmd: str) -> None:
    """Execute a local shell command and render it in a highly aesthetic panel."""
    from rich.panel import Panel
    from rich.text import Text
    import asyncio

    td = _terminal_display()
    console = td.get_console()

    theme_colors = {
        "sunset": "orange3",
        "cyberpunk": "deeppink",
        "aurora": "springgreen3",
        "monochrome": "grey70",
        "ocean": "dodgerblue3",
    }
    theme_accent = theme_colors.get(td._active_theme_name, "orange3")

    console.print(
        f"\n[bold {theme_accent}]⚙ 正在执行本地指令:[/bold {theme_accent}] [italic dim]{cmd}[/italic dim]"
    )

    # 异步执行 shell
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()
    exit_code = proc.returncode

    stdout_str = stdout.decode("utf-8", errors="replace")
    stderr_str = stderr.decode("utf-8", errors="replace")

    output_text = Text()
    if stdout_str:
        output_text.append(stdout_str)
    if stderr_str:
        if stdout_str:
            output_text.append("\n")
        output_text.append(stderr_str, style="bold red")

    if not stdout_str and not stderr_str:
        output_text.append("(无任何标准输出)", style="italic dim")

    status_icon = "✔" if exit_code == 0 else "✖"
    status_style = "green" if exit_code == 0 else "bold red"

    title = f"[{theme_accent}]Shell 穿透终端[/[{theme_accent}]]"
    subtitle = f"[{status_style}]{status_icon} 退出码: {exit_code}[/{status_style}]"

    panel = Panel(
        output_text,
        title=title,
        subtitle=subtitle,
        border_style=theme_accent,
        padding=(1, 2),
    )
    console.print(panel)
    console.print()


# ── Slash command helpers ────────────────────────────────────────────────

# Slash commands are defined in terminal_display


async def _resume_picker(
    arg: str,
    prompt_session: Any | None,
) -> Path | None:
    """Resolve a session log path via ``arg`` or interactive selection.

    Returns ``None`` if the user cancels, no logs exist, or the argument
    matches nothing — already prints the explanation in those cases.
    """
    from agent.core.session_resume import (
        format_session_log_entry,
        list_session_logs,
        resolve_session_log_arg,
    )
    from agent.core.session import DEFAULT_SESSION_LOG_DIR

    console = _terminal_display().get_console()
    directory = DEFAULT_SESSION_LOG_DIR
    entries = list_session_logs(directory)
    if not entries:
        console.print(f"[yellow]No session logs found in ./{directory}.[/yellow]")
        return None

    if arg:
        selected = resolve_session_log_arg(arg, entries, directory)
        if selected is None:
            console.print(f"[bold red]No matching session log:[/bold red] {arg}")
        return selected

    console.print()
    console.print("[bold]Saved sessions[/bold]")
    for index, entry in enumerate(entries, start=1):
        console.print(format_session_log_entry(index, entry))
    console.print()

    if prompt_session is None:
        console.print("[yellow]Cannot prompt for a selection here.[/yellow]")
        return None

    try:
        choice = await prompt_session.prompt_async(
            "Select session number (blank to cancel): "
        )
    except (EOFError, KeyboardInterrupt):
        console.print("[dim]Resume cancelled.[/dim]")
        return None
    choice = choice.strip()
    if not choice:
        console.print("[dim]Resume cancelled.[/dim]")
        return None
    selected = resolve_session_log_arg(choice, entries, directory)
    if selected is None:
        console.print(f"[bold red]Invalid selection:[/bold red] {choice}")
    return selected


async def _handle_slash_command(
    cmd: str,
    config,
    session_holder: list,
    submission_queue: asyncio.Queue,
    submission_id: list[int],
    prompt_session: Any | None = None,
) -> Submission | None:
    """
    Handle a slash command. Returns a Submission to enqueue, or None if
    the command was handled locally (caller should set turn_complete_event).

    Async because ``/model`` fires a probe ping to validate the model+effort
    combo before committing the switch.
    """
    td = _terminal_display()
    parts = cmd.strip().split(None, 1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "/help":
        td.print_help()
        return None

    if command == "/undo":
        submission_id[0] += 1
        return Submission(
            id=f"sub_{submission_id[0]}",
            operation=Operation(op_type=_op_type("UNDO")),
        )

    if command == "/compact":
        submission_id[0] += 1
        return Submission(
            id=f"sub_{submission_id[0]}",
            operation=Operation(op_type=_op_type("COMPACT")),
        )

    if command in {"/new", "/clear"}:
        session = session_holder[0] if session_holder else None
        if session is None:
            td.get_console().print("[bold red]No active session to reset.[/bold red]")
            return None
        submission_id[0] += 1
        return Submission(
            id=f"sub_{submission_id[0]}",
            operation=Operation(
                op_type=_op_type("NEW"),
                data={"clear_screen": command == "/clear"},
            ),
        )

    if command == "/resume":
        session = session_holder[0] if session_holder else None
        if session is None:
            td.get_console().print(
                "[bold red]No active session to restore into.[/bold red]"
            )
            return None
        selected_path = await _resume_picker(arg, prompt_session)
        if selected_path is None:
            return None
        submission_id[0] += 1
        return Submission(
            id=f"sub_{submission_id[0]}",
            operation=Operation(
                op_type=_op_type("RESUME"), data={"path": str(selected_path)}
            ),
        )

    if command == "/model":
        from agent.core import model_switcher
        from agent.core.hf_tokens import resolve_hf_token
        from agent.core.model_catalog import load_model_catalog, set_default_model

        console = td.get_console()
        if not arg or arg.lower() in {"list", "ls"}:
            model_switcher.print_model_listing(config, console)
            return None
        if arg.lower() == "status":
            catalog = load_model_catalog(config)
            console.print(f"[bold]Current model:[/bold] {config.model_name}")
            console.print(f"[bold]Default model:[/bold] {catalog.default or '(none)'}")
            console.print(f"[dim]Model file: {catalog.path}[/dim]")
            return None

        save_default = False
        selector = arg
        for prefix in ("--global ", "--save ", "--default "):
            if selector.startswith(prefix):
                save_default = True
                selector = selector[len(prefix) :].strip()
                break
        if selector in {"--global", "--save", "--default"}:
            console.print("[bold red]Missing model id after --global.[/bold red]")
            return None
        normalized = model_switcher.resolve_selector(selector, config)
        if not model_switcher.is_valid_model_id(normalized):
            model_switcher.print_invalid_id(selector, console)
            return None
        session = session_holder[0] if session_holder else None
        await model_switcher.probe_and_switch_model(
            normalized,
            config,
            session,
            console,
            resolve_hf_token(),
        )
        if config.model_name == normalized and save_default:
            path = set_default_model(normalized, config)
            console.print(f"[green]Default model saved:[/green] {normalized}")
            console.print(f"[dim]{path}[/dim]")
        return None

    if command == "/yolo":
        config.yolo_mode = not config.yolo_mode
        state = "ON" if config.yolo_mode else "OFF"
        print(f"YOLO mode: {state}")
        return None

    if command == "/effort":
        console = td.get_console()
        valid = {"minimal", "low", "medium", "high", "xhigh", "max", "off"}
        session = session_holder[0] if session_holder else None
        if not arg:
            current = config.reasoning_effort or "off"
            console.print(f"[bold]Reasoning effort preference:[/bold] {current}")
            if session and session.model_effective_effort:
                console.print("[dim]Probed per model:[/dim]")
                for m, eff in session.model_effective_effort.items():
                    console.print(f"  [dim]{m}: {eff or 'off'}[/dim]")
            console.print(
                "[dim]Set with '/effort minimal|low|medium|high|xhigh|max|off'. "
                "'max' is Anthropic-only; 'xhigh' is also supported by current "
                "OpenAI GPT-5 models. The cascade falls back to whatever the "
                "model actually accepts.[/dim]"
            )
            return None
        level = arg.lower()
        if level not in valid:
            console.print(f"[bold red]Invalid level:[/bold red] {arg}")
            console.print(f"[dim]Expected one of: {', '.join(sorted(valid))}[/dim]")
            return None
        config.reasoning_effort = None if level == "off" else level
        # Drop the per-model probe cache — the new preference may resolve
        # differently. Next ``/model`` (or the retry safety net) reprobes.
        if session is not None:
            session.model_effective_effort.clear()
        console.print(f"[green]Reasoning effort: {level}[/green]")
        if session is not None:
            console.print(
                "[dim]run /model <current> to re-probe, or send a message — "
                "the agent adjusts automatically if the new level isn't supported.[/dim]"
            )
        return None

    if command == "/status":
        session = session_holder[0] if session_holder else None
        print(f"Model: {config.model_name}")
        print(f"Reasoning effort: {config.reasoning_effort or 'off'}")
        print(f"Tool runtime: {_tool_runtime_label(_is_local_tool_runtime(config))}")
        if session:
            print(f"Turns: {session.turn_count}")
            print(f"Context items: {len(session.context_manager.items)}")
            td.print_context_status(session, include_turns=True, include_items=True)
        return None

    if command == "/usage":
        session = session_holder[0] if session_holder else None
        td.print_usage_status(session)
        return None

    if command == "/plan":
        td.print_plan()
        return None

    if command == "/theme":
        console = td.get_console()
        themes = td.get_theme_names()
        if not arg:
            console.print(
                "\n[bold rgb(255,200,80)]可用主题列表 (Available Themes):[/bold rgb(255,200,80)]"
            )
            for t in themes:
                color_map = {
                    "sunset": "bold rgb(255,180,80)",
                    "cyberpunk": "bold rgb(255,0,127)",
                    "aurora": "bold rgb(0,230,118)",
                    "monochrome": "bold white",
                    "ocean": "bold rgb(33,150,243)",
                }
                curr = " (当前激活)" if t == td._active_theme_name else ""
                console.print(
                    f"  • [{color_map.get(t, 'white')}]{t}[/{color_map.get(t, 'white')}]{curr}"
                )
            console.print(
                "\n[dim]切换主题请使用: [bold]/theme <theme_name>[/bold][/dim]\n"
            )
            return None

        success = td.set_theme(arg)
        if success:
            console.print(
                f"\n🧬 [bold rgb(80,200,120)]✔ 主题切换成功！[/bold rgb(80,200,120)] 当前主题已设为 [bold cyan]{arg.lower()}[/bold cyan]。\n"
            )
        else:
            console.print(f"\n✖ [bold red]无效的主题名:[/bold red] '{arg}'")
            console.print(f"[dim]可选主题: {', '.join(themes)}[/dim]\n")
        return None

    if command == "/share-traces":
        session = session_holder[0] if session_holder else None
        await _handle_share_traces_command(arg, config, session)
        return None

    if command == "/hf-token":
        console = td.get_console()
        if not arg:
            # 查看当前 Token 状态
            token = (
                getattr(config, "hf_token", None)
                or (
                    session_holder[0].hf_token
                    if (session_holder and session_holder[0])
                    else None
                )
                or resolve_hf_token()
            )
            if not token:
                console.print(
                    "\n[yellow]⚠ 当前未设置 Hugging Face Token。[/yellow] 一部分 Hub MCP 工具及 Sandbox 可能会受到限制。"
                )
                console.print(
                    "[dim]设置 Token 请使用: [bold]/hf-token <your_token>[/bold][/dim]\n"
                )
            else:
                validated_token, username = _validated_hf_token(token)
                if validated_token:
                    # 掩码显示
                    masked = (
                        token[:4] + "*" * (len(token) - 8) + token[-4:]
                        if len(token) > 8
                        else "****"
                    )
                    console.print(
                        "\n🧬 [bold rgb(80,200,120)]✔ Hugging Face Token 验证成功！[/bold rgb(80,200,120)]"
                    )
                    console.print(
                        f"  • 用户名 (User): [bold cyan]{username}[/bold cyan]"
                    )
                    console.print(f"  • 令牌 (Token): [dim]{masked}[/dim]\n")
                else:
                    console.print(
                        "\n✖ [bold red]当前载入的 Hugging Face Token 验证失败！[/bold red] 该 Token 可能是失效或过期的。"
                    )
                    console.print(
                        "[dim]重新设置请使用: [bold]/hf-token <your_token>[/bold][/dim]\n"
                    )
            return None

        # 设置新 Token
        new_token = arg.strip()
        console.print("[dim]正在与 Hugging Face 服务器握手验证...[/dim]")
        try:
            from huggingface_hub import HfApi, login

            # 实时握手验证
            user_info = HfApi(token=new_token).whoami()
            username = user_info.get("name", "unknown")

            # 保存到本地缓存
            try:
                login(token=new_token, add_to_git_credential=False)
                console.print(
                    "[dim]Token 已成功保存至 ~/.cache/huggingface/token[/dim]"
                )
            except Exception as e:
                console.print(
                    f"[yellow]Warning: could not persist token to cache ({e})[/yellow]"
                )

            # 热重载到当前 session 和 config 中
            config.hf_token = new_token
            session = session_holder[0] if session_holder else None
            if session:
                session.hf_token = new_token
                session.user_id = username
                if getattr(session, "tool_router", None):
                    session.tool_router.hf_token = new_token

            console.print(
                "\n🧬 [bold rgb(80,200,120)]✔ Hugging Face Token 动态设置并验证成功！[/bold rgb(80,200,120)]"
            )
            console.print(f"  • 用户名 (User): [bold cyan]{username}[/bold cyan]\n")

        except Exception as e:
            console.print(
                "\n✖ [bold red]Hugging Face Token 验证失败！[/bold red] 请检查令牌是否正确或网络状况。"
            )
            console.print(f"[dim]详细报错: {str(e)}[/dim]\n")
        return None

    print(f"Unknown command: {command}. Type /help for available commands.")
    return None


async def _handle_share_traces_command(arg: str, config, session) -> None:
    """Show or flip visibility of the user's personal trace dataset.

    Uses the user's own HF_TOKEN (write-scoped to their namespace). Only
    operates on the personal trace repo configured via
    ``personal_trace_repo_template`` — never touches the shared org dataset.
    """
    from agent.core.hf_tokens import resolve_hf_token
    from huggingface_hub import HfApi
    from huggingface_hub.utils import HfHubHTTPError

    console = _terminal_display().get_console()
    if session is None:
        console.print("[bold red]No active session.[/bold red]")
        return

    repo_id = session._personal_trace_repo_id() if session is not None else None
    if not repo_id:
        if not getattr(config, "share_traces", False):
            console.print(
                "[yellow]share_traces is disabled in config. "
                "Set it to true to publish per-session traces to your HF dataset."
                "[/yellow]"
            )
            return
        if not session.user_id:
            console.print(
                "[yellow]No HF username resolved \u2014 cannot pick a personal "
                "trace repo. Set HF_TOKEN to a token tied to your account.[/yellow]"
            )
            return
        console.print(
            "[yellow]personal_trace_repo_template is unset \u2014 nothing to do.[/yellow]"
        )
        return

    token = session.hf_token or resolve_hf_token()
    if not token:
        console.print(
            "[bold red]No HF_TOKEN available.[/bold red] Cannot read or change "
            "dataset visibility."
        )
        return

    api = HfApi(token=token)
    url = f"https://huggingface.co/datasets/{repo_id}"
    target = arg.strip().lower()

    if not target:
        try:
            info = await asyncio.to_thread(
                api.repo_info, repo_id=repo_id, repo_type="dataset"
            )
            visibility = "private" if getattr(info, "private", False) else "public"
            console.print(f"[bold]Trace dataset:[/bold] {url}")
            console.print(f"[bold]Visibility:[/bold] {visibility}")
            console.print(
                "[dim]Use '/share-traces public' to publish, "
                "'/share-traces private' to lock it back down.[/dim]"
            )
        except HfHubHTTPError as e:
            if getattr(e.response, "status_code", None) == 404:
                console.print(
                    f"[dim]Dataset {repo_id} doesn't exist yet \u2014 it'll be "
                    "created (private) on the next session save.[/dim]"
                )
            else:
                console.print(f"[bold red]Hub error:[/bold red] {e}")
        except Exception as e:
            console.print(f"[bold red]Could not fetch dataset info:[/bold red] {e}")
        return

    if target not in {"public", "private"}:
        console.print(
            f"[bold red]Unknown argument:[/bold red] {target}. "
            "Expected 'public' or 'private'."
        )
        return

    private = target == "private"
    try:
        # Idempotent — create if missing so first-flip works even before any
        # session has been saved yet.
        await asyncio.to_thread(
            api.create_repo,
            repo_id=repo_id,
            repo_type="dataset",
            private=private,
            token=token,
            exist_ok=True,
        )
        await asyncio.to_thread(
            api.update_repo_settings,
            repo_id=repo_id,
            repo_type="dataset",
            private=private,
            token=token,
        )
    except Exception as e:
        console.print(f"[bold red]Failed to update visibility:[/bold red] {e}")
        return

    label = "PUBLIC" if not private else "private"
    console.print(f"[green]Dataset is now {label}.[/green] {url}")


async def main(
    model: str | None = None,
    sandbox_tools: bool = False,
):
    """Interactive chat with the agent"""
    _configure_litellm_runtime()
    from agent.core.local_models import is_local_model_id
    from agent.core.openai_compatible_models import is_openai_compatible_model_id

    # Clear screen
    _clear_terminal()

    # Create prompt session for input (needed early for token prompt)
    from prompt_toolkit.history import FileHistory
    import os
    import inspect

    history_dir = os.path.expanduser("~/.aidd-intern")
    os.makedirs(history_dir, exist_ok=True)
    history_file = os.path.join(history_dir, "input_history")

    factory = _get_prompt_session_factory()
    # Safely pass history and completer only if supported by the factory (to handle test mocks gracefully)
    try:
        sig = inspect.signature(factory)
        supports_history = "history" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        supports_completer = "completer" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except Exception:
        supports_history = True
        supports_completer = True

    completer = TUICompleter()
    kwargs = {}
    if supports_history:
        kwargs["history"] = FileHistory(history_file)
    if supports_completer:
        kwargs["completer"] = completer
        kwargs["complete_while_typing"] = True

    prompt_session = factory(**kwargs)

    load_config_fn = _get_load_config()
    resolve_hf_token_fn = _get_resolve_hf_token()
    notification_gateway_cls = _get_notification_gateway_cls()
    banner_fn = _get_print_banner()

    config = load_config_fn(CLI_CONFIG_PATH, include_user_defaults=True)
    if model:
        config.model_name = model
    _apply_tool_runtime_override(config, sandbox_tools=sandbox_tools)
    local_mode = _is_local_tool_runtime(config)

    # 动态将 config 注入 completer
    completer.config = config

    # HF token — required for Hub-backed models/tools and sandbox tools, but
    # not for non-HF LLMs using only local filesystem tools.
    hf_token = resolve_hf_token_fn()
    non_hf_model = is_local_model_id(
        config.model_name
    ) or is_openai_compatible_model_id(config.model_name)

    # 启动时强反馈校验
    if hf_token:
        validated_tok, hf_user = _validated_hf_token(hf_token)
        if not validated_tok:
            from rich.console import Console

            Console().print(
                "\n[bold red]✖ 检测到本地缓存或环境变量中的 Hugging Face Token，但验证失败 (可能已过期或无效)！[/bold red]"
            )
            hf_token = None
            hf_user = None

    if not hf_token and (not non_hf_model or not local_mode):
        hf_token = await _prompt_and_save_hf_token(prompt_session)

    hf_token, hf_user = _validated_hf_token(hf_token)
    if not hf_token and (not non_hf_model or not local_mode):
        hf_token = await _prompt_and_save_hf_token(prompt_session)
        hf_token, hf_user = _validated_hf_token(hf_token)

    td = _terminal_display()
    banner_fn(
        model=config.model_name,
        hf_user=hf_user,
        tool_runtime=_tool_runtime_label(local_mode),
    )
    _maybe_print_update_notice()
    submission_loop_fn = _load_submission_loop()

    # Pre-warm the HF router catalog in the background so /model switches
    # don't block on a network fetch.
    from agent.core import hf_router_catalog

    asyncio.create_task(asyncio.to_thread(hf_router_catalog.prewarm))

    # Create queues for communication
    submission_queue = asyncio.Queue()
    event_queue = asyncio.Queue()

    # Events to signal agent state
    turn_complete_event = asyncio.Event()
    turn_complete_event.set()
    ready_event = asyncio.Event()

    notification_gateway = notification_gateway_cls(config.messaging)
    await notification_gateway.start()
    # Create tool router with the selected CLI tool runtime.
    tool_router = _create_tool_router(
        config.mcpServers,
        hf_token=hf_token,
        local_mode=local_mode,
    )

    # Session holder for interrupt/model/status access
    session_holder = [None]

    agent_task = asyncio.create_task(
        submission_loop_fn(
            submission_queue,
            event_queue,
            config=config,
            tool_router=tool_router,
            session_holder=session_holder,
            hf_token=hf_token,
            user_id=hf_user,
            local_mode=local_mode,
            stream=True,
            notification_gateway=notification_gateway,
            notification_destinations=config.messaging.default_auto_destinations(),
            defer_turn_complete_notification=True,
        )
    )

    # Start event listener in background
    listener_task = asyncio.create_task(
        event_listener(
            event_queue,
            submission_queue,
            turn_complete_event,
            ready_event,
            prompt_session,
            config,
            session_holder=session_holder,
        )
    )

    await ready_event.wait()

    submission_id = [0]
    # Mirrors codex-rs/tui/src/bottom_pane/mod.rs:137
    # (`QUIT_SHORTCUT_TIMEOUT = Duration::from_secs(1)`). Two Ctrl+C presses
    # within this window quit; a single press cancels the in-flight turn.
    CTRL_C_QUIT_WINDOW = 1.0
    # Hint string matches codex-rs/tui/src/bottom_pane/footer.rs:746
    # (`" again to quit"` prefixed with the key binding, rendered dim).
    CTRL_C_HINT = "[dim]ctrl + c again to quit[/dim]"
    interrupt_state = {"last": 0.0, "exit": False}

    loop = asyncio.get_running_loop()

    def _on_sigint() -> None:
        """SIGINT handler — fires while the agent is generating (terminal is
        in cooked mode between prompts). Mirrors Codex's `on_ctrl_c` in
        codex-rs/tui/src/chatwidget.rs: first press cancels active work and
        arms the quit hint; second press within the window quits."""
        now = time.monotonic()
        session = session_holder[0]

        if now - interrupt_state["last"] < CTRL_C_QUIT_WINDOW:
            interrupt_state["exit"] = True
            if session:
                session.cancel()
            # Wake the main loop out of turn_complete_event.wait()
            turn_complete_event.set()
            return

        interrupt_state["last"] = now
        if session and not session.is_cancelled:
            session.cancel()
        td.get_console().print(f"\n{CTRL_C_HINT}")

    def _install_sigint() -> bool:
        try:
            loop.add_signal_handler(signal.SIGINT, _on_sigint)
            return True
        except (NotImplementedError, RuntimeError):
            return False  # Windows or non-main thread

    # prompt_toolkit's prompt_async installs its own SIGINT handler and, on
    # exit, calls loop.remove_signal_handler(SIGINT) — which wipes ours too.
    # So we re-arm at the top of every loop iteration, right before the busy
    # wait. Without this, Ctrl+C during agent streaming after the first turn
    # falls through to the default handler and the terminal just echoes ^C.
    sigint_available = _install_sigint()

    try:
        while True:
            if sigint_available:
                _install_sigint()

            # 动态向 completer 注入 session_holder
            if hasattr(prompt_session, "completer") and prompt_session.completer:
                prompt_session.completer.session_holder = session_holder

            try:
                await turn_complete_event.wait()
            except asyncio.CancelledError:
                break
            turn_complete_event.clear()

            if interrupt_state["exit"]:
                break

            # Get user input. prompt_toolkit puts the terminal in raw mode and
            # installs its own SIGINT handling; ^C arrives as \x03 and surfaces
            # as KeyboardInterrupt here. On return, prompt_toolkit removes the
            # loop's SIGINT handler — we re-arm at the top of the next iter.
            session = session_holder[0] if session_holder else None
            try:
                user_input = await get_user_input(prompt_session, session=session)
            except EOFError:
                break
            except KeyboardInterrupt:
                now = time.monotonic()
                if now - interrupt_state["last"] < CTRL_C_QUIT_WINDOW:
                    break
                interrupt_state["last"] = now
                td.get_console().print(CTRL_C_HINT)
                turn_complete_event.set()
                continue

            # A successful read ends the double-press window — an unrelated
            # Ctrl+C during the next turn should start a fresh arming.
            interrupt_state["last"] = 0.0

            # Check for exit commands
            if user_input.strip().lower() in ["exit", "quit", "/quit", "/exit"]:
                break

            # Skip empty input
            if not user_input.strip():
                turn_complete_event.set()
                continue

            # Handle local shell escape command via '!'
            if user_input.strip().startswith("!"):
                cmd = user_input.strip()[1:].strip()
                if cmd:
                    await _execute_local_shell_command(cmd)
                else:
                    td.get_console().print(
                        "[yellow]⚠ 缺少可执行的 Shell 命令。示例: !git status[/yellow]"
                    )
                turn_complete_event.set()
                continue

            # Handle slash commands
            if user_input.strip().startswith("/"):
                sub = await _handle_slash_command(
                    user_input.strip(),
                    config,
                    session_holder,
                    submission_queue,
                    submission_id,
                    prompt_session,
                )
                if sub is None:
                    # Command handled locally, loop back for input
                    turn_complete_event.set()
                    continue
                else:
                    await submission_queue.put(sub)
                    continue

            # Submit to agent
            submission_id[0] += 1
            submission = Submission(
                id=f"sub_{submission_id[0]}",
                operation=Operation(
                    op_type=_op_type("USER_INPUT"), data={"text": user_input}
                ),
            )
            await submission_queue.put(submission)

    except KeyboardInterrupt:
        pass
    finally:
        if sigint_available:
            try:
                loop.remove_signal_handler(signal.SIGINT)
            except (NotImplementedError, RuntimeError):
                pass

    # Shutdown
    shutdown_submission = Submission(
        id="sub_shutdown", operation=Operation(op_type=_op_type("SHUTDOWN"))
    )
    await submission_queue.put(shutdown_submission)

    # Wait for agent to finish (the listener must keep draining events
    # or the agent will block on event_queue.put)
    try:
        await asyncio.wait_for(agent_task, timeout=10.0)
    except asyncio.TimeoutError:
        agent_task.cancel()
        # Agent didn't shut down cleanly — close MCP explicitly
        await tool_router.__aexit__(None, None, None)
    finally:
        await notification_gateway.close()

    # Now safe to cancel the listener (agent is done emitting events)
    listener_task.cancel()

    td.get_console().print("\n[dim]Bye.[/dim]\n")


async def headless_main(
    prompt: str,
    model: str | None = None,
    max_iterations: int | None = None,
    stream: bool = True,
    sandbox_tools: bool = False,
) -> None:
    """Run a single prompt headlessly and exit."""
    import logging

    logging.basicConfig(level=logging.WARNING)
    _configure_runtime_logging()
    from agent.core.local_models import is_local_model_id
    from agent.core.openai_compatible_models import is_openai_compatible_model_id

    load_config_fn = _get_load_config()
    resolve_hf_token_fn = _get_resolve_hf_token()
    notification_gateway_cls = _get_notification_gateway_cls()

    config = load_config_fn(CLI_CONFIG_PATH, include_user_defaults=True)
    config.yolo_mode = True  # Auto-approve everything in headless mode

    if model:
        config.model_name = model
    _apply_tool_runtime_override(config, sandbox_tools=sandbox_tools)
    local_mode = _is_local_tool_runtime(config)

    hf_token = resolve_hf_token_fn()
    non_hf_model = is_local_model_id(
        config.model_name
    ) or is_openai_compatible_model_id(config.model_name)
    if not hf_token and (not non_hf_model or not local_mode):
        print(
            "ERROR: No HF token found. Set HF_TOKEN or run `hf auth login`.",
            file=sys.stderr,
        )
        sys.exit(1)

    hf_token, hf_user = _validated_hf_token(hf_token)
    if not hf_token and (not non_hf_model or not local_mode):
        print(
            "ERROR: HF token is missing or invalid. Set HF_TOKEN or run `hf auth login`.",
            file=sys.stderr,
        )
        sys.exit(1)

    if hf_token:
        print("HF token loaded", file=sys.stderr)

    notification_gateway = notification_gateway_cls(config.messaging)
    await notification_gateway.start()

    if max_iterations is not None:
        config.max_iterations = max_iterations

    print(f"Model: {config.model_name}", file=sys.stderr)
    print(f"Tool runtime: {_tool_runtime_label(local_mode)}", file=sys.stderr)
    print(f"Max iterations: {config.max_iterations}", file=sys.stderr)
    print(f"Prompt: {prompt}", file=sys.stderr)
    print("---", file=sys.stderr)

    submission_queue: asyncio.Queue = asyncio.Queue()
    event_queue: asyncio.Queue = asyncio.Queue()

    submission_loop_fn = _load_submission_loop()
    tool_router = _create_tool_router(
        config.mcpServers,
        hf_token=hf_token,
        local_mode=local_mode,
    )
    session_holder: list = [None]

    agent_task = asyncio.create_task(
        submission_loop_fn(
            submission_queue,
            event_queue,
            config=config,
            tool_router=tool_router,
            session_holder=session_holder,
            hf_token=hf_token,
            user_id=hf_user,
            local_mode=local_mode,
            stream=stream,
            notification_gateway=notification_gateway,
            notification_destinations=config.messaging.default_auto_destinations(),
            defer_turn_complete_notification=True,
        )
    )

    # Wait for ready
    while True:
        event = await event_queue.get()
        if event.event_type == "ready":
            break

    # Submit the prompt
    submission = Submission(
        id="sub_1",
        operation=Operation(op_type=_op_type("USER_INPUT"), data={"text": prompt}),
    )
    await submission_queue.put(submission)

    # Process events until turn completes. Headless mode is for scripts /
    # log capture: no shimmer animation, no typewriter, no live-redrawing
    # research overlay. Output is plain, append-only text.
    console = _create_rich_console()
    stream_buf = _StreamBuffer(console)
    _hl_last_tool = [None]
    _hl_sub_id = [1]
    # Research sub-agent tool calls are buffered per agent_id and dumped as
    # a static block once each sub-agent finishes, instead of streaming via
    # the live redrawing SubAgentDisplayManager (which is TTY-only).
    _hl_research_buffers: dict[str, dict] = {}

    while True:
        event = await event_queue.get()

        if event.event_type == "assistant_chunk":
            content = event.data.get("content", "") if event.data else ""
            if content:
                stream_buf.add_chunk(content)
                await stream_buf.flush_ready(instant=True)
        elif event.event_type == "assistant_stream_end":
            await stream_buf.finish(instant=True)
        elif event.event_type == "assistant_message":
            content = event.data.get("content", "") if event.data else ""
            if content:
                await _terminal_display().print_markdown(content, instant=True)
        elif event.event_type == "tool_call":
            stream_buf.discard()
            tool_name = event.data.get("tool", "") if event.data else ""
            arguments = event.data.get("arguments", {}) if event.data else {}
            if tool_name:
                _hl_last_tool[0] = tool_name
                if tool_name != "research":
                    args_str = json.dumps(arguments)[:80]
                    _terminal_display().print_tool_call(tool_name, args_str)
        elif event.event_type == "tool_output":
            output = event.data.get("output", "") if event.data else ""
            success = event.data.get("success", False) if event.data else False
            duration_s = event.data.get("duration_s", 0.0) if event.data else 0.0
            _terminal_display().print_tool_duration(
                _hl_last_tool[0], success, duration_s
            )
            if _hl_last_tool[0] == "plan_tool" and output:
                _terminal_display().print_tool_output(
                    output, success, truncate=False, duration_s=0.0
                )
        elif event.event_type == "tool_log":
            tool = event.data.get("tool", "") if event.data else ""
            log = event.data.get("log", "") if event.data else ""
            if not log:
                pass
            elif tool == "research":
                agent_id = event.data.get("agent_id", "") if event.data else ""
                label = event.data.get("label", "") if event.data else ""
                aid = agent_id or "research"
                if log == "Starting research sub-agent...":
                    _hl_research_buffers[aid] = {
                        "label": label or "research",
                    }
                elif log == "Research complete.":
                    buf = _hl_research_buffers.pop(aid, None)
                    if buf is not None:
                        f = _terminal_display().get_console().file
                        f.write(
                            f"  \033[38;2;120;200;140m✓\033[0m \033[2m{buf['label']}\033[0m\n"
                        )
                        f.flush()
                elif log.startswith("tokens:") or log.startswith("tools:"):
                    pass
                elif aid in _hl_research_buffers:
                    pass
                else:
                    pass
            else:
                _terminal_display().print_tool_log(tool, log)
        elif event.event_type == "approval_required":
            # Auto-approve in headless mode, except scheduled HF jobs. Those
            # are rejected because their recurring cost needs manual approval.
            tools_data = event.data.get("tools", []) if event.data else []
            approvals = [
                {
                    "tool_call_id": t.get("tool_call_id", ""),
                    "approved": not _is_scheduled_hf_job_tool(t),
                    "feedback": (
                        "Scheduled HF jobs require manual approval."
                        if _is_scheduled_hf_job_tool(t)
                        else None
                    ),
                }
                for t in tools_data
            ]
            _hl_sub_id[0] += 1
            await submission_queue.put(
                Submission(
                    id=f"hl_approval_{_hl_sub_id[0]}",
                    operation=Operation(
                        op_type=_op_type("EXEC_APPROVAL"),
                        data={"approvals": approvals},
                    ),
                )
            )
        elif event.event_type == "compacted":
            old_tokens = event.data.get("old_tokens", 0) if event.data else 0
            new_tokens = event.data.get("new_tokens", 0) if event.data else 0
            _terminal_display().print_compacted(old_tokens, new_tokens)
        elif event.event_type == "error":
            stream_buf.discard()
            error = (
                event.data.get("error", "Unknown error")
                if event.data
                else "Unknown error"
            )
            _terminal_display().print_error(error)
            break
        elif event.event_type in ("turn_complete", "interrupted"):
            stream_buf.discard()
            history_size = event.data.get("history_size", "?") if event.data else "?"
            print(
                f"\n--- Agent {event.event_type} (history_size={history_size}) ---",
                file=sys.stderr,
            )
            if event.event_type == "turn_complete":
                session = session_holder[0] if session_holder else None
                if session is not None:
                    await session.send_deferred_turn_complete_notification(event)
            break

    # Shutdown
    shutdown_submission = Submission(
        id="sub_shutdown", operation=Operation(op_type=_op_type("SHUTDOWN"))
    )
    await submission_queue.put(shutdown_submission)

    try:
        await asyncio.wait_for(agent_task, timeout=10.0)
    except asyncio.TimeoutError:
        agent_task.cancel()
        await tool_router.__aexit__(None, None, None)
    finally:
        await notification_gateway.close()


def cli():
    """Entry point for the aidd-intern CLI command."""
    import logging as _logging
    import warnings

    # Suppress aiohttp "Unclosed client session" noise during event loop teardown
    _logging.getLogger("asyncio").setLevel(_logging.CRITICAL)
    _configure_runtime_logging()
    # Suppress litellm pydantic deprecation warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="litellm")
    # Suppress whoosh invalid escape sequence warnings (third-party, unfixed upstream)
    warnings.filterwarnings("ignore", category=SyntaxWarning, module="whoosh")

    parser = argparse.ArgumentParser(description="aidd-intern CLI")

    # Interactive/Headless (default if no command)
    parser.add_argument(
        "prompt_or_command",
        nargs="?",
        default=None,
        help="Run headlessly with this prompt, or a sub-command (update, configure-llm, doctor, prepare)",
    )
    parser.add_argument(
        "--model", "-m", default=None, help="Model to use (default: from config)"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Max LLM requests per turn (default: 50, use -1 for unlimited)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable token streaming (use non-streaming LLM calls)",
    )
    parser.add_argument(
        "--sandbox-tools",
        action="store_true",
        help="Use HF Space sandbox tools instead of local filesystem tools",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run local installation diagnostics and exit",
    )

    # Arguments for 'update' command
    parser.add_argument(
        "--check", action="store_true", help="[update] Check for updates"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="[update] Print update commands"
    )
    parser.add_argument(
        "--with-frontend",
        action="store_true",
        help="[update] Also refresh frontend dependencies",
    )

    # Arguments for 'prepare' command
    parser.add_argument(
        "--prepare-aidd",
        action="store_true",
        help=(
            "Run the local AIDD preparation stage: literature metadata, PDB "
            "download, structure crop, and hotspot residue ranking"
        ),
    )
    parser.add_argument(
        "--target-name",
        default=None,
        help="Target name for --prepare-aidd, e.g. PD-L1",
    )
    parser.add_argument(
        "--pdb-id",
        default=None,
        help="RCSB PDB id for --prepare-aidd, e.g. 4ZQK",
    )
    parser.add_argument(
        "--target-chains",
        default=None,
        help="Comma-separated target chain ids for --prepare-aidd, e.g. A",
    )
    parser.add_argument(
        "--partner-chains",
        default=None,
        help="Comma-separated partner chain ids for --prepare-aidd, e.g. B",
    )
    parser.add_argument(
        "--residue-ranges",
        default=None,
        help="Optional crop ranges for --prepare-aidd, e.g. A:19-134",
    )
    parser.add_argument(
        "--research-query",
        default=None,
        help="Optional literature query for --prepare-aidd",
    )
    parser.add_argument(
        "--prep-project-dir",
        default=None,
        help="Optional output directory for --prepare-aidd artifacts",
    )
    parser.add_argument(
        "--literature-limit",
        type=int,
        default=5,
        help="Number of literature metadata results for --prepare-aidd",
    )
    parser.add_argument(
        "--hotspot-cutoff",
        type=float,
        default=4.5,
        help="Atom contact cutoff in Angstrom for --prepare-aidd hotspot ranking",
    )

    # The 'configure-llm' command takes a provider as a positional arg
    # which conflicts with 'prompt_or_command' if we're not careful.
    # We'll handle it manually.
    args, unknown = parser.parse_known_args()

    # 首次使用交互式模型及 API 密钥配置引导
    from agent.utils.cli_ops import (
        needs_interactive_setup,
        run_interactive_first_run_setup,
    )

    if needs_interactive_setup(args):
        run_interactive_first_run_setup()

    # 首次下载或启动时自动检查更新并交互式询问升级
    if not args.prompt_or_command or args.prompt_or_command not in (
        "doctor",
        "update",
        "configure-llm",
        "prepare",
    ):
        from agent.utils.cli_ops import maybe_interactive_update

        maybe_interactive_update()

    try:
        if args.prompt_or_command == "doctor" or args.doctor:
            from agent.core.doctor import run_doctor

            raise SystemExit(run_doctor())
        elif args.prompt_or_command == "update":
            from agent.utils.cli_ops import run_update

            raise SystemExit(
                run_update(
                    check=args.check,
                    dry_run=args.dry_run,
                    with_frontend=args.with_frontend,
                )
            )
        elif args.prompt_or_command == "configure-llm":
            from agent.utils.cli_ops import run_configure_llm

            provider = unknown[0] if unknown else None
            raise SystemExit(run_configure_llm(provider))
        elif args.prompt_or_command == "prepare" or args.prepare_aidd:
            from agent.tools.aidd_prepare_tool import run_aidd_preparation_cli

            raise SystemExit(
                asyncio.run(
                    run_aidd_preparation_cli(
                        target_name=args.target_name,
                        pdb_id=args.pdb_id,
                        target_chains=args.target_chains,
                        partner_chains=args.partner_chains,
                        project_dir=args.prep_project_dir,
                        residue_ranges=args.residue_ranges,
                        research_query=args.research_query,
                        literature_limit=args.literature_limit,
                        hotspot_cutoff=args.hotspot_cutoff,
                    )
                )
            )
        elif args.prompt_or_command:
            # Check if it's a known command that didn't match above (e.g. typos or future commands)
            # Otherwise treat it as a prompt.
            max_iter = args.max_iterations
            if max_iter is not None and max_iter < 0:
                max_iter = 10_000  # effectively unlimited
            asyncio.run(
                headless_main(
                    args.prompt_or_command,
                    model=args.model,
                    max_iterations=max_iter,
                    stream=not args.no_stream,
                    sandbox_tools=args.sandbox_tools,
                )
            )
        else:
            asyncio.run(
                main(
                    model=args.model,
                    sandbox_tools=args.sandbox_tools,
                )
            )
    except KeyboardInterrupt:
        print("\n\nGoodbye!")


if __name__ == "__main__":
    cli()
