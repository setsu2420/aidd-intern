"""
Terminal display utilities — rich-powered CLI formatting.
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.markdown import Heading, Markdown
from rich.panel import Panel
from rich.theme import Theme

try:
    from aidd_intern_core import clip_ansi_string as _rust_clip_ansi_string
    from aidd_intern_core import visible_width as _rust_visible_width  # noqa: F401

    _RUST_ANSI_AVAILABLE = True
except ImportError:
    _RUST_ANSI_AVAILABLE = False


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

    When the Rust core is available, delegates to the native implementation
    which uses unicode-width for CJK-aware column counting and runs without
    the GIL.
    """
    if _RUST_ANSI_AVAILABLE:
        try:
            return _rust_clip_ansi_string(s, width)
        except Exception:
            pass
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
        out.append("\033[0m\u2026")
    return "".join(out)


THEMES = {
    "sunset": {
        "tool.name": "bold rgb(255,180,80)",
        "tool.args": "dim rgb(220,200,180)",
        "tool.ok": "bold rgb(120,220,140)",
        "tool.fail": "bold rgb(255,100,100)",
        "context.ok": "dim green",
        "context.warn": "bold yellow",
        "context.danger": "bold red",
        "info": "dim",
        "muted": "dim",
        "markdown.strong": "bold rgb(255,183,77)",
        "markdown.emphasis": "italic rgb(255,224,178)",
        "markdown.code": "bold rgb(128,222,234)",
        "markdown.code_block": "rgb(224,242,241)",
        "markdown.link": "underline rgb(41,182,246)",
        "markdown.h1": "bold rgb(255,140,0)",
        "markdown.h2": "bold rgb(255,180,50)",
        "markdown.h3": "bold rgb(255,200,100)",
    },
    "cyberpunk": {
        "tool.name": "bold rgb(255,0,127)",
        "tool.args": "dim rgb(0,255,255)",
        "tool.ok": "bold rgb(57,255,20)",
        "tool.fail": "bold rgb(255,7,58)",
        "context.ok": "dim rgb(0,255,255)",
        "context.warn": "bold rgb(255,255,0)",
        "context.danger": "bold rgb(255,7,58)",
        "info": "dim rgb(0,255,255)",
        "muted": "dim rgb(180,180,180)",
        "markdown.strong": "bold rgb(255,0,127)",
        "markdown.emphasis": "italic rgb(0,255,255)",
        "markdown.code": "bold rgb(255,255,0)",
        "markdown.code_block": "rgb(20,20,40)",
        "markdown.link": "underline rgb(0,255,255)",
        "markdown.h1": "bold rgb(255,0,127)",
        "markdown.h2": "bold rgb(0,255,255)",
        "markdown.h3": "bold rgb(255,255,0)",
    },
    "aurora": {
        "tool.name": "bold rgb(0,230,118)",
        "tool.args": "dim rgb(186,104,200)",
        "tool.ok": "bold rgb(0,229,255)",
        "tool.fail": "bold rgb(255,23,68)",
        "context.ok": "dim rgb(0,229,255)",
        "context.warn": "bold rgb(255,235,59)",
        "context.danger": "bold rgb(255,23,68)",
        "info": "dim rgb(0,230,118)",
        "muted": "dim rgb(160,180,170)",
        "markdown.strong": "bold rgb(0,230,118)",
        "markdown.emphasis": "italic rgb(186,104,200)",
        "markdown.code": "bold rgb(224,64,251)",
        "markdown.code_block": "rgb(30,40,45)",
        "markdown.link": "underline rgb(0,229,255)",
        "markdown.h1": "bold rgb(0,230,118)",
        "markdown.h2": "bold rgb(0,229,255)",
        "markdown.h3": "bold rgb(186,104,200)",
    },
    "monochrome": {
        "tool.name": "bold white",
        "tool.args": "dim gray",
        "tool.ok": "bold rgb(240,240,240)",
        "tool.fail": "bold rgb(150,150,150)",
        "context.ok": "dim gray",
        "context.warn": "bold white",
        "context.danger": "bold white underline",
        "info": "dim",
        "muted": "dim",
        "markdown.strong": "bold white",
        "markdown.emphasis": "italic rgb(200,200,200)",
        "markdown.code": "bold rgb(220,220,220)",
        "markdown.code_block": "rgb(20,20,20)",
        "markdown.link": "underline white",
        "markdown.h1": "bold white",
        "markdown.h2": "bold rgb(200,200,200)",
        "markdown.h3": "bold rgb(160,160,160)",
    },
    "ocean": {
        "tool.name": "bold rgb(33,150,243)",
        "tool.args": "dim rgb(178,223,219)",
        "tool.ok": "bold rgb(76,175,80)",
        "tool.fail": "bold rgb(244,67,54)",
        "context.ok": "dim rgb(178,223,219)",
        "context.warn": "bold rgb(255,152,0)",
        "context.danger": "bold rgb(244,67,54)",
        "info": "dim rgb(33,150,243)",
        "muted": "dim rgb(150,180,200)",
        "markdown.strong": "bold rgb(33,150,243)",
        "markdown.emphasis": "italic rgb(178,223,219)",
        "markdown.code": "bold rgb(0,188,212)",
        "markdown.code_block": "rgb(224,242,241)",
        "markdown.link": "underline rgb(33,150,243)",
        "markdown.h1": "bold rgb(13,71,161)",
        "markdown.h2": "bold rgb(25,118,210)",
        "markdown.h3": "bold rgb(30,136,229)",
    },
}

_active_theme_name = "sunset"
_has_custom_theme = False


def _get_theme_save_path() -> Path:
    p = Path.home() / ".aidd-intern"
    p.mkdir(parents=True, exist_ok=True)
    return p / "theme.txt"


def load_saved_theme() -> str:
    path = _get_theme_save_path()
    if path.exists():
        try:
            theme_val = path.read_text(encoding="utf-8").strip().lower()
            if theme_val in THEMES:
                return theme_val
        except Exception:
            pass
    return "sunset"


def save_theme(theme_name: str) -> None:
    try:
        path = _get_theme_save_path()
        path.write_text(theme_name, encoding="utf-8")
    except Exception:
        pass


def set_theme(theme_name: str) -> bool:
    global _active_theme_name, _has_custom_theme
    t_name = theme_name.strip().lower()
    if t_name not in THEMES:
        return False

    _active_theme_name = t_name

    if _has_custom_theme:
        try:
            _console.pop_theme()
        except Exception:
            pass

    _console.push_theme(Theme(THEMES[t_name]))
    _has_custom_theme = True
    save_theme(t_name)
    return True


def get_theme_names() -> list[str]:
    return list(THEMES.keys())


_THEME = Theme(THEMES["sunset"])
_console = Console(theme=_THEME, highlight=False)
set_theme(load_saved_theme())


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


def format_context_status_html(session: Any) -> Any:
    from prompt_toolkit.formatted_text import HTML

    status = _context_status(session)
    config = getattr(session, "config", None)

    # 1. 取得主题名
    theme_label = _active_theme_name.upper()

    # 2. 取得 Model 和 YOLO
    model_name = "unknown"
    yolo_active = False
    tool_runtime_str = "local"
    if config:
        model_name = getattr(config, "model_name", "unknown")
        if "/" in model_name:
            model_name = model_name.split("/")[-1]
        yolo_active = getattr(config, "yolo_mode", False)
        tool_runtime_str = getattr(config, "tool_runtime", "local")

    # 3. 取得累计 token 消耗
    total_tokens_consumed = 0
    llm_calls_count = 0
    if getattr(session, "logged_events", None):
        llm_calls = [
            e for e in session.logged_events if e.get("event_type") == "llm_call"
        ]
        total_tokens_consumed = sum(
            int((e.get("data") or {}).get("total_tokens") or 0) for e in llm_calls
        )
        llm_calls_count = len(llm_calls)

    # 4. 取得 Context tokens 占比和进度条
    percent = 0.0
    used_tokens = 0
    max_tokens = 0
    if status:
        percent = float(status["percent"])
        used_tokens = int(status["used_tokens"])
        max_tokens = int(status["max_tokens"])

    # 平滑进度条
    width = 10
    filled = int(round(max(0.0, min(percent, 100.0)) / 100.0 * width))
    bar = "█" * filled + "░" * (width - filled)

    # YOLO气泡配色
    if yolo_active:
        yolo_html = '<style bg="ansigreen" fg="ansiwhite"><b> YOLO </b></style>'
    else:
        yolo_html = '<style bg="ansigray" fg="ansiwhite"><b> YOLO </b></style>'

    # Sandbox气泡配色
    if tool_runtime_str == "sandbox":
        sandbox_html = '<style bg="ansipurple" fg="ansiwhite"><b> SANDBOX </b></style>'
    else:
        sandbox_html = '<style bg="ansiblue" fg="ansiwhite"><b> FILESYSTEM </b></style>'

    # 主题不同，状态栏色调也不同
    theme_colors = {
        "sunset": ("#FFA726", "#FFFFFF", "#FFA726"),
        "cyberpunk": ("#FF007F", "#FFFFFF", "#00FFFF"),
        "aurora": ("#00E676", "#FFFFFF", "#00E5FF"),
        "monochrome": ("#FFFFFF", "#000000", "#B0B0B0"),
        "ocean": ("#2196F3", "#FFFFFF", "#00BCD4"),
    }

    primary_color, text_color, accent_color = theme_colors.get(
        _active_theme_name, ("#FFA726", "#FFFFFF", "#FFA726")
    )

    # 使用 prompt_toolkit 能够理解的 style
    html_str = (
        f'<style bg="{primary_color}" fg="{text_color}"><b> AIDD-INTERN </b></style>'
        f'<style bg="#333333" fg="#E0E0E0"> {model_name} </style> '
        f"{yolo_html}"
        f"{sandbox_html} "
        f'<style bg="#444444" fg="#80D8FF"> <b>Tokens:</b> {_format_token_count(total_tokens_consumed)} </style>'
        f'<style bg="#222222" fg="#BDBDBD"> 🧪 Calls: {llm_calls_count} </style> | '
        f'<style fg="{accent_color}"><b>Context</b></style> '
        f'<style fg="{accent_color}">{bar}</style> '
        f'<style fg="#E0E0E0"><b>{_format_token_count(used_tokens)}</b>/{_format_token_count(max_tokens)} ({percent:.1f}%)</style> | '
        f'<style fg="#9E9E9E">Theme: <b>{theme_label}</b></style>'
    )

    return HTML(html_str)


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


def print_usage_status(session: Any) -> None:
    """Print complete token and cost usage report (Hermes Agent style)."""
    status = _context_status(session)
    if status is None:
        _console.print(
            f"{_I}[bold red]No active session or context manager available.[/bold red]"
        )
        return

    used_tokens = int(status["used_tokens"])
    max_tokens = int(status["max_tokens"])
    threshold = int(status["threshold"])
    percent = float(status["percent"])

    # Gather all llm_call events from session.logged_events
    llm_calls = []
    if getattr(session, "logged_events", None):
        llm_calls = [
            e for e in session.logged_events if e.get("event_type") == "llm_call"
        ]

    total_prompt = sum(
        int((e.get("data") or {}).get("prompt_tokens") or 0) for e in llm_calls
    )
    total_completion = sum(
        int((e.get("data") or {}).get("completion_tokens") or 0) for e in llm_calls
    )
    total_overall = sum(
        int((e.get("data") or {}).get("total_tokens") or 0) for e in llm_calls
    )
    total_cache_read = sum(
        int((e.get("data") or {}).get("cache_read_tokens") or 0) for e in llm_calls
    )
    total_cache_creation = sum(
        int((e.get("data") or {}).get("cache_creation_tokens") or 0) for e in llm_calls
    )
    total_cost = sum(
        float((e.get("data") or {}).get("cost_usd") or 0.0) for e in llm_calls
    )

    # Print general usage header
    _console.print()
    _console.print(
        f"{_I}[bold rgb(255,200,80)]=== Session Token & Cost Usage Report ===[/bold rgb(255,200,80)]"
    )

    # Render Context Footprint Status
    text = (
        f"Context Window: {_context_bar(percent)} {_format_token_count(used_tokens)} / "
        f"{_format_token_count(max_tokens)} ({percent:.1f}%)"
    )
    if threshold and threshold != max_tokens:
        text += f" | compact @ {_format_token_count(threshold)}"
    style = _context_status_style(percent)
    _console.print(f"{_I}[{style}]{escape(text)}[/{style}]")
    _console.print(
        f"{_I}[muted]Active context items: {status['items']} | turns: {status['turns']}[/muted]"
    )
    _console.print()

    # Render Session Aggregated Spend
    _console.print(f"{_I}[bold]Cumulative Session Metrics:[/bold]")
    _console.print(
        f"{_I}  • [bold cyan]Total Estimated Cost:[/bold cyan] [green]${total_cost:.5f}[/green]"
    )
    _console.print(f"{_I}  • [bold cyan]Total LLM Calls:[/bold cyan] {len(llm_calls)}")
    _console.print(
        f"{_I}  • [bold cyan]Total Tokens Transferred:[/bold cyan] {total_overall:,} tokens"
    )
    _console.print(f"{_I}    - [muted]Prompt input tokens:[/muted] {total_prompt:,}")
    _console.print(
        f"{_I}    - [muted]Completion output tokens:[/muted] {total_completion:,}"
    )
    _console.print(f"{_I}  • [bold cyan]Prompt Caching Efficiency:[/bold cyan]")
    _console.print(
        f"{_I}    - [green]Cache hit (read) tokens:[/green] {total_cache_read:,}"
    )
    _console.print(
        f"{_I}    - [yellow]Cache miss (written) tokens:[/yellow] {total_cache_creation:,}"
    )

    if not llm_calls:
        _console.print()
        _console.print(f"{_I}[dim]No LLM calls recorded in this session yet.[/dim]")
        _console.print()
        return

    # Render Rich Table of all LLM calls
    from rich.table import Table

    table = Table(
        title="LLM Call Trace History",
        title_justify="left",
        expand=False,
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
    )
    table.add_column("#", justify="right")
    table.add_column("Model", style="cyan")
    table.add_column("Kind", style="blue")
    table.add_column("Latency", justify="right", style="green")
    table.add_column("Prompt Tokens", justify="right")
    table.add_column("Completion Tokens", justify="right")
    table.add_column("Cache Hit", justify="right", style="dim green")
    table.add_column("Cost", justify="right", style="bold green")

    for idx, e in enumerate(llm_calls, 1):
        data = e.get("data") or {}
        model = data.get("model", "unknown")
        kind = data.get("kind", "main")
        latency = f"{data.get('latency_ms', 0):,}ms"
        prompt_tk = f"{data.get('prompt_tokens', 0):,}"
        completion_tk = f"{data.get('completion_tokens', 0):,}"
        cache_hit = f"{data.get('cache_read_tokens', 0):,}"
        cost = f"${data.get('cost_usd', 0.0):.5f}"

        table.add_row(
            str(idx), model, kind, latency, prompt_tk, completion_tk, cache_hit, cost
        )

    _console.print()
    _console.print(table)
    _console.print()


# ── Banner ─────────────────────────────────────────────────────────────


def print_banner(
    model: str | None = None,
    hf_user: str | None = None,
    tool_runtime: str | None = None,
) -> None:
    """Print particle logo then CRT boot sequence with system info."""
    model_label = model or "unknown"

    try:
        from aidd_intern_core import save_json_atomic  # noqa: F401

        rust_status = (
            "[bold rgb(80,200,120)]Rust native Core active[/bold rgb(80,200,120)]"
        )
    except ImportError:
        rust_status = "[bold rgb(255,180,50)]Python fallback[/bold rgb(255,180,50)]"

    # 主题不同，采用对应的渐变和高亮色
    theme_rgb = {
        "sunset": "rgb(255,180,80)",
        "cyberpunk": "rgb(255,0,127)",
        "aurora": "rgb(0,230,118)",
        "monochrome": "rgb(255,255,255)",
        "ocean": "rgb(33,150,243)",
    }
    theme_dim_rgb = {
        "sunset": "rgb(180,120,40)",
        "cyberpunk": "rgb(180,0,90)",
        "aurora": "rgb(0,160,80)",
        "monochrome": "rgb(120,120,120)",
        "ocean": "rgb(20,100,180)",
    }

    color = theme_rgb.get(_active_theme_name, "rgb(255,200,80)")
    dim_color = theme_dim_rgb.get(_active_theme_name, "rgb(180,140,40)")

    logo = (
        f"[bold {color}]"
        "       ___   ____ ___   ___         ____      __                 \n"
        "      /   | /  _// __ \\ / __ \\       /  _/___  / /_ ___  _________ \n"
        "     / /| | / / / / / // / / /______ / // __ \\/ __// _ \\/ ___/ __ \\\n"
        "    / ___ |/ / / /_/ // /_/ /_____// // / / / /_ /  __/ /  / / / /\n"
        "   /_/  |_/___/_____//_____/     /___/_/ /_/\\__/ \\___/_/  /_/ /_/ \n"
        f"[/bold {color}]"
    )

    card_content = (
        f"  • [bold cyan]Model:[/bold cyan]       {model_label}\n"
        f"  • [bold cyan]Sandbox:[/bold cyan]     {tool_runtime or 'local filesystem'}\n"
        f"  • [bold cyan]Acceleration:[/bold cyan] {rust_status}\n"
        f"  • [bold cyan]Tools Status:[/bold cyan] Tools: loading..."
    )

    from rich.panel import Panel
    from rich import box

    status_panel = Panel(
        card_content,
        title=f"[bold {color}]Runtime System Card[/bold {color}]",
        title_align="left",
        border_style=f"dim {dim_color}",
        box=box.ROUNDED,
        expand=False,
    )

    if not _boot_animation_enabled():
        _console.print()
        _console.print(logo)
        _console.print(status_panel)
        _console.print()
        return

    from agent.utils.particle_logo import run_particle_logo

    # Particle coalesce logo — 1.5s converge, 2s hold
    run_particle_logo(_console, hold_seconds=2.0)

    # Clear screen for CRT boot — starts from top
    _console.file.write("\033[2J\033[H")
    _console.file.flush()

    # Render ASCII logo and panel immediately after CRT boot warm-up
    _console.print(logo)
    _console.print(status_panel)
    _console.print()


# ── Init progress ──────────────────────────────────────────────────────


def print_init_done(tool_count: int = 0) -> None:
    color = {
        "sunset": "rgb(255,180,80)",
        "cyberpunk": "rgb(255,0,127)",
        "aurora": "rgb(0,230,118)",
        "monochrome": "rgb(255,255,255)",
        "ocean": "rgb(33,150,243)",
    }.get(_active_theme_name, "rgb(255,200,80)")

    _console.print(
        f"{_I}[bold rgb(80,200,120)]✔[/bold rgb(80,200,120)] [bold]Tools initialized successfully.[/bold] "
        f"[dim](Tools: {tool_count} loaded)[/dim]"
    )
    _console.print(
        f"{_I}[dim]Type [bold {color}]/help[/bold {color}] for commands · "
        f"[bold {color}]/model[/bold {color}] to switch models · "
        f"[bold {color}]/quit[/bold {color}] to exit[/dim]"
    )
    _console.print(f"{_I}[bold {color}]Intern Ready.[/bold {color}]\n")


# ── Tool calls ─────────────────────────────────────────────────────────


def print_tool_call(tool_name: str, args_preview: str) -> None:
    icon = "⚙️"
    name_lower = tool_name.lower()
    if "search" in name_lower or "grep" in name_lower:
        icon = "🔍"
    elif "file" in name_lower or "write" in name_lower or "replace" in name_lower:
        icon = "💾"
    elif "run" in name_lower or "execute" in name_lower or "command" in name_lower:
        icon = "💻"
    elif "read" in name_lower or "view" in name_lower:
        icon = "📖"
    elif "mcp" in name_lower:
        icon = "🔌"

    # 使用简洁内联流打印，而不是庞大圆角 Panel
    _console.print()
    _console.print(
        f"{_I}{icon} [tool.name]运行工具: {tool_name}[/tool.name] "
        f"[tool.args]{escape(args_preview)}[/tool.args]"
    )


def print_tool_duration(tool_name: str, success: bool, duration_s: float) -> None:
    if duration_s <= 0:
        return
    icon = "[tool.ok]✔[/tool.ok]" if success else "[tool.fail]✖[/tool.fail]"
    _console.print(
        f"{_I}  {icon} [tool.name]{tool_name}[/tool.name] "
        f"[dim]执行完毕，耗时[/dim] [bold]{duration_s:.2f}s[/bold]"
    )


def print_tool_output(
    output: str, success: bool, truncate: bool = True, duration_s: float = 0.0
) -> None:
    raw_output = output
    if not raw_output.strip():
        return

    total_lines = len(raw_output.split("\n"))

    if truncate:
        output = _truncate(output, max_lines=10)

    truncated_lines = total_lines - 10
    truncation_footer = ""
    if truncate and truncated_lines > 0:
        truncation_footer = (
            f"  ·  [dim]... (已省略多余的 {truncated_lines} 行日志)[/dim]"
        )

    icon = "[tool.ok]✔[/tool.ok]" if success else "[tool.fail]✖[/tool.fail]"
    status_text = f"{icon} [dim]执行完毕"
    if duration_s > 0:
        status_text += f" (耗时 {duration_s:.2f}s)"
    status_text += "[/dim]"
    if truncation_footer:
        status_text += truncation_footer

    from rich.panel import Panel
    from rich import box

    indented_output = "\n".join(f"  {line}" for line in output.split("\n"))

    output_panel = Panel(
        indented_output,
        title="[bold rgb(160,160,160)]工具执行结果[/bold rgb(160,160,160)]",
        title_align="left",
        subtitle=status_text,
        subtitle_align="left",
        border_style="dim gray" if success else "dim red",
        box=box.MINIMAL,
        expand=False,
    )

    _console.print(f"{_I}", output_panel)
    _console.print()


class SubAgentDisplayManager:
    """Manages multiple concurrent sub-agent displays with live spinner and active tool calls.

    Each agent gets its own stats and rolling tool-call log.
    All agents are rendered together so terminal escape-code
    erase/redraw stays consistent.
    """

    _MAX_VISIBLE = 4  # tool-call lines shown per agent
    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        self._agents: dict[str, dict] = {}  # agent_id -> state dict
        self._lines_on_screen = 0
        self._spinner_idx = 0
        self._loop_task: "asyncio.Task | None" = None

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

        if self._loop_task is None:
            try:
                loop = asyncio.get_running_loop()
                self._loop_task = loop.create_task(self._spinner_loop())
            except RuntimeError:
                pass

    async def _spinner_loop(self):
        try:
            while self._agents:
                self._spinner_idx = (self._spinner_idx + 1) % len(self._FRAMES)
                self._redraw()
                await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            self._loop_task = None

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
        line = f"{_I}\033[38;2;100;200;120m✔\033[0m \033[1;38;2;220;220;220m{label}\033[0m \033[38;2;140;140;140m已就绪\033[0m"
        if stats:
            line += f"  \033[2;38;2;140;140;140m({stats})\033[0m"
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
        """Render one concise research-agent status line with live spinner and recent calls."""
        stats = self._format_stats(agent)
        label = agent["label"]
        frame = self._FRAMES[self._spinner_idx]
        header = f"{_I}\033[38;2;255;200;80m{frame}\033[0m \033[1;38;2;240;240;240m{label}\033[0m"
        if stats:
            header += f"  \033[2;38;2;140;140;140m({stats})\033[0m"

        lines = [header]
        if not compact:
            # 仅展示最近 3 次工具调用，限制在 MAX_VISIBLE - 1 行
            visible_calls = agent["calls"][-3:]
            for call in visible_calls:
                lines.append(
                    f"{_I}  \033[2;38;2;120;120;120m↳\033[0m \033[2;38;2;180;180;180m{call}\033[0m"
                )
        return lines

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
        theme=Theme(THEMES[_active_theme_name]),
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
    ("/resume", "[index|id|path]", "Pick up from ~/.aidd-intern/session_logs"),
    ("/model", "[id]", "Show available models or switch"),
    (
        "/effort",
        "[level]",
        "Set reasoning effort preference",
    ),
    ("/yolo", "", "Toggle auto-approve mode"),
    ("/status", "", "Current model & turn count"),
    ("/usage", "", "Show detailed token consumption and costs"),
    ("/plan", "", "Show the current execution stages and plan"),
    (
        "/share-traces",
        "[public|private]",
        "Show or change HF trace visibility",
    ),
    (
        "/theme",
        "[name]",
        "List available themes or switch (sunset|cyberpunk|aurora|monochrome|ocean)",
    ),
    (
        "/hf-token",
        "[token]",
        "Show, validate or dynamically set Hugging Face token",
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
        _console.print(
            "[bold rgb(255,200,80)]Current Active Plan:[/bold rgb(255,200,80)]"
        )
        _console.print(plan_str)
    else:
        _console.print(
            "[dim]No active plan. Use plan_tool to create a plan (Research -> Strategy -> Execution -> Validation).[/dim]"
        )


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
