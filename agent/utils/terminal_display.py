"""
Terminal display utilities — rich-powered CLI formatting.
"""

import asyncio
import os
import re
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.markdown import Heading, Markdown
from rich.panel import Panel
from rich.theme import Theme


class _LeftHeading(Heading):
    """Rich's default Markdown renders h1/h2 centered via Align.center.
    Yield the styled text directly so headings stay left-aligned."""

    def __rich_console__(self, console, options):
        self.text.justify = "left"
        yield self.text


Markdown.elements["heading_open"] = _LeftHeading


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clip_to_width(s: str, width: int) -> str:
    """Truncate a string to `width` visible columns, preserving ANSI styles.

    Needed for the sub-agent live redraw: cursor-up-and-erase assumes one
    logical line == one terminal row. If a line wraps, cursor-up undershoots
    and the next redraw corrupts the display. Truncating prevents wrap.
    """
    if width <= 0:
        return s
    out: list[str] = []
    visible = 0
    i = 0
    # Reserve 1 char for the trailing ellipsis
    limit = width - 1
    truncated = False
    while i < len(s):
        m = _ANSI_RE.match(s, i)
        if m:
            out.append(m.group())
            i = m.end()
            continue
        if visible >= limit:
            truncated = True
            break
        out.append(s[i])
        visible += 1
        i += 1
    if truncated:
        # Strip styles (so ellipsis isn't left hanging inside a style run)
        out.append("\033[0m…")
    return "".join(out)


_THEME = Theme(
    {
        "tool.name": "bold rgb(255,200,80)",
        "tool.args": "dim",
        "tool.ok": "dim green",
        "tool.fail": "dim red",
        "context.ok": "dim green",
        "context.warn": "bold yellow",
        "context.danger": "bold red",
        "info": "dim",
        "muted": "dim",
        # Markdown emphasis colors
        "markdown.strong": "bold rgb(255,200,80)",
        "markdown.emphasis": "italic rgb(180,140,40)",
        "markdown.code": "rgb(120,220,255)",
        "markdown.code_block": "rgb(120,220,255)",
        "markdown.link": "underline rgb(90,180,255)",
        "markdown.h1": "bold rgb(255,200,80)",
        "markdown.h2": "bold rgb(240,180,95)",
        "markdown.h3": "bold rgb(220,165,100)",
    }
)

_console = Console(theme=_THEME, highlight=False)

# Indent prefix for all agent output (aligns under the `>` prompt)
_I = "  "

_BOOT_ANIMATION_ENV = "AIDD_INTERN_BOOT_ANIMATION"
_TUI_TYPEWRITER_ENV = "AIDD_INTERN_TUI_TYPEWRITER"


def _boot_animation_enabled() -> bool:
    value = os.environ.get(_BOOT_ANIMATION_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _typewriter_enabled() -> bool:
    value = os.environ.get(_TUI_TYPEWRITER_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_console() -> Console:
    return _console


def _format_token_count(tokens: int) -> str:
    value = abs(tokens)
    if value >= 1_000_000:
        formatted = f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        formatted = f"{value / 1_000:.1f}k"
    else:
        formatted = str(value)
    return f"-{formatted}" if tokens < 0 else formatted


def _context_bar(percent: float, width: int = 12) -> str:
    clamped = max(0.0, min(percent, 100.0))
    filled = int(round(clamped / 100.0 * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def _context_status(session: Any) -> dict[str, Any] | None:
    cm = getattr(session, "context_manager", None)
    config = getattr(session, "config", None)
    if cm is None or config is None:
        return None

    model_name = getattr(config, "model_name", "")
    used_tokens = cm.estimate_usage(model_name)
    max_tokens = int(getattr(cm, "model_max_tokens", 0) or 0)
    threshold = int(getattr(cm, "compaction_threshold", max_tokens) or max_tokens)
    percent = (used_tokens / max_tokens * 100.0) if max_tokens else 0.0

    return {
        "used_tokens": used_tokens,
        "max_tokens": max_tokens,
        "threshold": threshold,
        "percent": percent,
        "turns": int(getattr(session, "turn_count", 0) or 0),
        "items": len(getattr(cm, "items", []) or []),
    }


def format_context_status(
    session: Any,
    *,
    include_turns: bool = False,
    include_items: bool = False,
) -> str | None:
    status = _context_status(session)
    if status is None:
        return None

    used_tokens = int(status["used_tokens"])
    max_tokens = int(status["max_tokens"])
    threshold = int(status["threshold"])
    percent = float(status["percent"])

    text = (
        f"Context {_context_bar(percent)} {_format_token_count(used_tokens)} / "
        f"{_format_token_count(max_tokens)} ({percent:.1f}%)"
    )
    if threshold and threshold != max_tokens:
        text += f" | compact @ {_format_token_count(threshold)}"
    if max_tokens and used_tokens > max_tokens:
        text += f" | over by {_format_token_count(used_tokens - max_tokens)}"
    if include_turns:
        text += f" | turns {status['turns']}"
    if include_items:
        text += f" | items {status['items']}"
    return text


def _context_status_style(percent: float) -> str:
    if percent >= 90.0:
        return "context.danger"
    if percent >= 75.0:
        return "context.warn"
    return "context.ok"


def print_context_status(
    session: Any,
    *,
    include_turns: bool = False,
    include_items: bool = False,
) -> None:
    status = _context_status(session)
    if status is None:
        return
    text = format_context_status(
        session,
        include_turns=include_turns,
        include_items=include_items,
    )
    if text:
        style = _context_status_style(float(status["percent"]))
        _console.print(f"{_I}[{style}]{escape(text)}[/{style}]")


# ── Banner ─────────────────────────────────────────────────────────────


def print_banner(
    model: str | None = None,
    hf_user: str | None = None,
    tool_runtime: str | None = None,
) -> None:
    """Print particle logo then CRT boot sequence with system info."""
    model_label = model or "unknown"
    user_label = hf_user or "not logged in"
    if not _boot_animation_enabled():
        _console.print()
        _console.print(f"{_I}[tool.name]aidd-intern[/tool.name] runtime starting...")
        _console.print(f"{_I}[muted]User:[/muted] {user_label}")
        _console.print(f"{_I}[muted]Model:[/muted] {model_label}")
        _console.print(
            f"{_I}[muted]Tool runtime:[/muted] {tool_runtime or 'local filesystem'}"
        )
        _console.print(f"{_I}[muted]Tools:[/muted] loading...")
        _console.print()
        _console.print(
            f"{_I}[tool.name]/help[/tool.name] [muted]for commands[/muted] · "
            f"[tool.name]/model[/tool.name] [muted]to switch[/muted] · "
            f"[tool.name]/quit[/tool.name] [muted]to exit[/muted]"
        )
        return

    from agent.utils.particle_logo import run_particle_logo
    from agent.utils.crt_boot import run_boot_sequence

    # Particle coalesce logo — 1.5s converge, 2s hold
    run_particle_logo(_console, hold_seconds=2.0)

    # Clear screen for CRT boot — starts from top
    _console.file.write("\033[2J\033[H")
    _console.file.flush()

    # Warm gold palette matching the shimmer highlight (255, 200, 80)
    gold = "rgb(255,200,80)"
    dim_gold = "rgb(180,140,40)"

    boot_lines = [
        (f"{_I}aidd-intern runtime starting...", gold),
        (f"{_I}  User: {user_label}", dim_gold),
        (f"{_I}  Model: {model_label}", dim_gold),
        (f"{_I}  Tool runtime: {tool_runtime or 'local filesystem'}", dim_gold),
        (f"{_I}  Tools: loading...", dim_gold),
        ("", ""),
        (f"{_I}/help for commands · /model to switch · /quit to exit", gold),
    ]

    run_boot_sequence(_console, boot_lines)


# ── Init progress ──────────────────────────────────────────────────────


def print_init_done(tool_count: int = 0) -> None:
    _console.print(f"{_I}[muted]Tools:[/muted] {tool_count} loaded")
    _console.print(
        f"{_I}[tool.name]/help[/tool.name] [muted]for commands[/muted] · "
        f"[tool.name]/model[/tool.name] [muted]to switch[/muted] · "
        f"[tool.name]/quit[/tool.name] [muted]to exit[/muted]"
    )
    _console.print(f"{_I}[tool.name]Ready.[/tool.name]")


# ── Tool calls ─────────────────────────────────────────────────────────


def print_tool_call(tool_name: str, args_preview: str) -> None:
    f = _console.file
    f.write(
        f"{_I}\033[38;2;255;200;80m▸ {tool_name}\033[0m  \033[2m{args_preview}\033[0m\n"
    )
    f.flush()


def print_tool_output(output: str, success: bool, truncate: bool = True) -> None:
    if truncate:
        output = _truncate(output, max_lines=10)
    style = "tool.ok" if success else "tool.fail"
    # Indent each line of tool output
    indented = "\n".join(f"{_I}  {line}" for line in output.split("\n"))
    _console.print(f"[{style}]{indented}[/{style}]")


class SubAgentDisplayManager:
    """Manages multiple concurrent sub-agent displays.

    Each agent gets its own stats and rolling tool-call log.
    All agents are rendered together so terminal escape-code
    erase/redraw stays consistent.
    """

    _MAX_VISIBLE = 4  # tool-call lines shown per agent

    def __init__(self):
        self._agents: dict[str, dict] = {}  # agent_id -> state dict
        self._lines_on_screen = 0

    def start(self, agent_id: str, label: str = "research") -> None:
        import time

        self._agents[agent_id] = {
            "label": label,
            "calls": [],
            "tool_count": 0,
            "token_count": 0,
            "start_time": time.monotonic(),
        }
        self._redraw()

    def set_tokens(self, agent_id: str, tokens: int) -> None:
        if agent_id in self._agents:
            self._agents[agent_id]["token_count"] = tokens

    def set_tool_count(self, agent_id: str, count: int) -> None:
        if agent_id in self._agents:
            self._agents[agent_id]["tool_count"] = count

    def add_call(self, agent_id: str, tool_desc: str) -> None:
        if agent_id in self._agents:
            self._agents[agent_id]["calls"].append(tool_desc)
            self._redraw()

    def clear(self, agent_id: str) -> None:
        # On completion: erase the live region, freeze a single-line summary
        # for this agent ("✓ research: … (stats)") above the live region so
        # the user sees each sub-agent finish cleanly without the tool-call
        # noise, then redraw remaining live agents.
        agent = self._agents.pop(agent_id, None)
        self._erase()
        if agent is not None:
            width = max(10, _console.width)
            line = _clip_to_width(self._render_completion_line(agent), width)
            _console.file.write(line + "\n")
            _console.file.flush()
        self._lines_on_screen = 0
        if self._agents:
            self._redraw()

    @staticmethod
    def _render_completion_line(agent: dict) -> str:
        stats = SubAgentDisplayManager._format_stats(agent)
        label = agent["label"]
        # dim green check + dim label; stats in parens
        line = f"{_I}\033[38;2;120;200;140m✓\033[0m \033[2m{label}\033[0m"
        if stats:
            line += f"  \033[2m({stats})\033[0m"
        return line

    @staticmethod
    def _format_stats(agent: dict) -> str:
        import time

        start = agent["start_time"]
        if start is None:
            return ""
        elapsed = time.monotonic() - start
        if elapsed < 60:
            time_str = f"{elapsed:.0f}s"
        else:
            time_str = f"{elapsed / 60:.0f}m {elapsed % 60:.0f}s"
        return time_str

    def _erase(self) -> None:
        if self._lines_on_screen > 0:
            f = _console.file
            for _ in range(self._lines_on_screen):
                f.write("\033[A\033[K")
            f.flush()

    def _render_agent_lines(self, agent: dict, compact: bool = False) -> list[str]:
        """Render one concise research-agent status line."""
        stats = self._format_stats(agent)
        label = agent["label"]
        header = f"{_I}\033[38;2;255;200;80m▸ {label}\033[0m"
        if stats:
            header += f"  \033[2m({stats})\033[0m"
        return [header]

    def _redraw(self) -> None:
        f = _console.file
        self._erase()
        compact = len(self._agents) > 1
        width = max(10, _console.width)
        lines: list[str] = []
        for agent in self._agents.values():
            for ln in self._render_agent_lines(agent, compact=compact):
                lines.append(_clip_to_width(ln, width))
        for line in lines:
            f.write(line + "\n")
        f.flush()
        self._lines_on_screen = len(lines)


_subagent_display = SubAgentDisplayManager()


def print_tool_log(tool: str, log: str, agent_id: str = "", label: str = "") -> None:
    """Handle tool log events — sub-agent calls get the rolling display."""
    if tool == "research":
        aid = agent_id or "research"
        if log == "Starting research sub-agent...":
            _subagent_display.start(aid, label or "research")
        elif log == "Research complete.":
            _subagent_display.clear(aid)
        elif log.startswith("tokens:"):
            _subagent_display.set_tokens(aid, int(log[7:]))
        elif log.startswith("tools:"):
            _subagent_display.set_tool_count(aid, int(log[6:]))
        else:
            _subagent_display.add_call(aid, log)
    else:
        _console.print(f"{_I}[dim]{tool}: {log}[/dim]")


# ── Messages ───────────────────────────────────────────────────────────


async def print_markdown(
    text: str,
    cancel_event: "asyncio.Event | None" = None,
    instant: bool = False,
) -> None:
    import io
    from rich.padding import Padding

    _console.print()

    # Render markdown to a string buffer so we can type it out
    buf = io.StringIO()
    # Important: StringIO is not a TTY, so Rich would normally strip styles.
    # Force terminal rendering so ANSI style codes are preserved for typewriter output.
    buf_console = Console(
        file=buf,
        width=_console.width,
        highlight=False,
        theme=_THEME,
        force_terminal=True,
        color_system=_console.color_system or "truecolor",
    )
    buf_console.print(Padding(Markdown(text), (0, 0, 0, 2)))
    rendered = buf.getvalue()

    # Strip trailing whitespace from each line so we don't type across the full width
    lines = rendered.split("\n")
    rendered = "\n".join(line.rstrip() for line in lines)

    f = _console.file

    # Default TUI path is buffered: streaming already arrives in paragraph-sized
    # chunks, and per-character flush loops make terminals feel sluggish.
    if instant or not _typewriter_enabled():
        f.write(rendered)
        f.write("\n")
        f.flush()
        return

    import random

    # CRT typewriter effect — async so the event loop can service signal
    # handlers (Ctrl+C during streaming) between characters. If cancelled
    # mid-type, stop cleanly: write an ANSI reset so half-open color state
    # doesn't bleed onto the "interrupted" line, and return.
    rng = random.Random(42)
    cancelled = False
    chunk_size = 24
    for offset in range(0, len(rendered), chunk_size):
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        chunk = rendered[offset : offset + chunk_size]
        f.write(chunk)
        f.flush()
        pause = 0.0015 if ("\n" in chunk or " " in chunk) else 0.003
        if rng.random() < 0.05:
            pause *= 2
        await asyncio.sleep(pause)
    f.write("\033[0m\n" if cancelled else "\n")
    f.flush()


def print_error(message: str) -> None:
    _console.print(f"\n{_I}[bold red]Error:[/bold red] {message}")


def print_turn_complete() -> None:
    pass  # no separator — clean output


def print_interrupted() -> None:
    _console.print(f"\n{_I}[dim italic]interrupted[/dim italic]")


def print_compacted(old_tokens: int, new_tokens: int) -> None:
    # Compaction is internal context maintenance. Keep it out of normal output.
    return


# ── Approval ───────────────────────────────────────────────────────────


def print_approval_header(count: int) -> None:
    label = f"Approval required — {count} item{'s' if count != 1 else ''}"
    _console.print()
    _console.print(
        f"{_I}",
        Panel(
            f"[bold yellow]{label}[/bold yellow]", border_style="yellow", expand=False
        ),
    )


def print_approval_item(index: int, total: int, tool_name: str, operation: str) -> None:
    _console.print(
        f"\n{_I}[bold]\\[{index}/{total}][/bold]  [tool.name]{tool_name}[/tool.name]  {operation}"
    )


def print_yolo_approve(count: int) -> None:
    _console.print(
        f"{_I}[bold yellow]yolo →[/bold yellow] auto-approved {count} item(s)"
    )


# ── Help ───────────────────────────────────────────────────────────────

HELP_ROWS: tuple[tuple[str, str, str], ...] = (
    ("/help", "", "Show this help"),
    ("/new", "", "Start a fresh chat"),
    ("/clear", "", "Clear terminal and start fresh"),
    ("/undo", "", "Undo last turn"),
    ("/compact", "", "Compact context window"),
    ("/resume", "[index|id|path]", "Pick up from ./session_logs"),
    ("/model", "[id]", "Show available models or switch"),
    (
        "/effort",
        "[level]",
        "Set reasoning effort preference",
    ),
    ("/yolo", "", "Toggle auto-approve mode"),
    ("/status", "", "Current model & turn count"),
    (
        "/share-traces",
        "[public|private]",
        "Show or change HF trace visibility",
    ),
    ("/quit", "", "Exit"),
)


def _help_column_widths(
    rows: tuple[tuple[str, str, str], ...],
) -> tuple[int, int]:
    return (
        max(len(command) for command, _, _ in rows),
        max(len(args) for _, args, _ in rows),
    )


def _format_help_row(
    command: str,
    args: str,
    description: str,
    command_width: int,
    args_width: int,
) -> str:
    command_gap = " " * (command_width - len(command) + 2)
    args_gap = " " * (args_width - len(args) + 2)
    command_markup = f"[cyan]{escape(command)}[/cyan]"
    args_markup = f"[muted]{escape(args)}[/muted]" if args else ""
    return f"{_I}  {command_markup}{command_gap}{args_markup}{args_gap}{description}"


def format_help_text(rows: tuple[tuple[str, str, str], ...] | None = None) -> str:
    help_rows = HELP_ROWS if rows is None else rows
    command_width, args_width = _help_column_widths(help_rows)
    return "\n".join(
        [f"{_I}[bold]Commands[/bold]"]
        + [
            _format_help_row(
                command,
                args,
                description,
                command_width,
                args_width,
            )
            for command, args, description in help_rows
        ]
    )


def print_help() -> None:
    _console.print()
    _console.print(format_help_text())
    _console.print()


# ── Plan display ───────────────────────────────────────────────────────


def format_plan_display() -> str:
    """Format the current plan for display."""
    from agent.tools.plan_tool import get_current_plan

    plan = get_current_plan()
    if not plan:
        return ""

    completed = [t for t in plan if t["status"] == "completed"]
    in_progress = [t for t in plan if t["status"] == "in_progress"]
    pending = [t for t in plan if t["status"] == "pending"]

    lines = []
    for t in completed:
        lines.append(f"{_I}[green]✓[/green] [dim]{t['content']}[/dim]")
    for t in in_progress:
        lines.append(f"{_I}[yellow]▸[/yellow] {t['content']}")
    for t in pending:
        lines.append(f"{_I}[dim]○ {t['content']}[/dim]")

    summary = f"[dim]{len(completed)}/{len(plan)} done[/dim]"
    lines.append(f"{_I}{summary}")
    return "\n".join(lines)


def print_plan() -> None:
    plan_str = format_plan_display()
    if plan_str:
        _console.print(plan_str)


# ── Formatting for plan_tool output (used by plan_tool handler) ────────


def format_plan_tool_output(todos: list) -> str:
    if not todos:
        return "Plan is empty."

    lines = ["Plan updated:", ""]
    completed = [t for t in todos if t["status"] == "completed"]
    in_progress = [t for t in todos if t["status"] == "in_progress"]
    pending = [t for t in todos if t["status"] == "pending"]

    for t in completed:
        lines.append(f"  [x] {t['id']}. {t['content']}")
    for t in in_progress:
        lines.append(f"  [~] {t['id']}. {t['content']}")
    for t in pending:
        lines.append(f"  [ ] {t['id']}. {t['content']}")

    lines.append(f"\n{len(completed)}/{len(todos)} done")
    return "\n".join(lines)


# ── Internal helpers ───────────────────────────────────────────────────


def _truncate(text: str, max_lines: int = 6) -> str:
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
