"""
Local tool implementations — bash/read/write/edit running on the user's machine.

Drop-in replacement for sandbox tools when running in CLI (local) mode.
Same tool specs (names, parameters) but handlers execute locally via
subprocess/pathlib instead of going through a remote sandbox.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agent.core.hub_artifacts import wrap_shell_command_with_hub_artifact_bootstrap

logger = logging.getLogger(__name__)


MAX_OUTPUT_CHARS = 25_000
MAX_LINE_LENGTH = 4000
DEFAULT_READ_LINES = 2000
DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 36000  # 10 hours — needed for long training runs (e.g. PostTrainBench)
MAX_COMMAND_LENGTH = 10_000

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07")

# ── Dangerous command detection ────────────────────────────────────────

_DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"rm\s+(-[^\s]*\s+)*-rf\s+/(?!\S)"),
        "recursive force-delete root filesystem",
    ),
    (re.compile(r"rm\s+(-[^\s]*\s+)*-rf\s+~"), "recursive force-delete home directory"),
    (re.compile(r"curl\s.*\|\s*(?:ba)?sh"), "piping remote script to shell"),
    (re.compile(r"wget\s.*\|\s*(?:ba)?sh"), "piping remote script to shell"),
    (re.compile(r"chmod\s+777"), "setting world-writable permissions"),
    (re.compile(r"dd\s+if="), "raw disk write via dd"),
    (re.compile(r"mkfs\."), "filesystem format command"),
    (re.compile(r":\(\)\{\s*:\|:\&\s*\}\s*;"), "fork bomb"),
    (re.compile(r">\s*/dev/sd[a-z]"), "overwriting block device"),
    (re.compile(r"mv\s+/\s"), "moving root filesystem"),
]


def _check_dangerous_command(command: str) -> tuple[bool, str]:
    """Check if a command matches known dangerous patterns.

    Returns:
        (is_dangerous, reason)
    """
    for pattern, reason in _DANGEROUS_PATTERNS:
        if pattern.search(command):
            return True, reason
    return False, ""


def _check_path_safety(path_str: str) -> tuple[bool, str]:
    """Check if the path is safely confined to the workspace or temporary directories.

    Returns:
        (is_safe, error_msg)
    """
    if not path_str:
        return False, "No path provided."
    try:
        p = Path(path_str).resolve()

        # Allowed roots
        workspace_root = Path("/home/xxue/aidd-intern").resolve()
        tmp_dir = Path("/tmp").resolve()
        var_tmp_dir = Path("/var/tmp").resolve()

        # Helper to check if a path is under a parent
        def is_under(path: Path, parent: Path) -> bool:
            try:
                path.relative_to(parent)
                return True
            except ValueError:
                return False

        # Also allow path matching temporary directory from tempfile
        try:
            import tempfile

            sys_tmp = Path(tempfile.gettempdir()).resolve()
            if is_under(p, sys_tmp) or p == sys_tmp:
                return True, ""
        except Exception:
            pass

        if is_under(p, workspace_root) or p == workspace_root:
            return True, ""
        if is_under(p, tmp_dir) or p == tmp_dir:
            return True, ""
        if is_under(p, var_tmp_dir) or p == var_tmp_dir:
            return True, ""

        return (
            False,
            f"❌ Permission denied: Access restricted. Path '{path_str}' is outside the allowed workspace '/home/xxue/aidd-intern' or '/tmp' boundaries.",
        )
    except Exception as e:
        return False, f"❌ Path validation error: {e}"


# Track files that have been read this session (enforces read-before-write/edit)
_files_read: set[str] = set()


def _resolve_path(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except Exception:
        return path


def _atomic_write(path: Path, content: str) -> None:
    """Write file atomically via temp file + os.replace().

    Ensures the file is never left in a partial/corrupted state — it's either
    the old content or the new content, never half-written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(tmp_path, str(path))
        tmp_path = None  # successfully replaced, nothing to clean up
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _truncate_output(
    output: str, max_chars: int = MAX_OUTPUT_CHARS, head_ratio: float = 0.25
) -> str:
    """Tail-biased truncation with temp file spillover for full output access."""
    if len(output) <= max_chars:
        return output
    # Write full output to temp file so LLM can read specific sections
    spill_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix="bash_output_", delete=False
        ) as f:
            f.write(output)
            spill_path = f.name
        # Note: we need to import or reference _check_path_safety logic if needed,
        # but spill_path is in /tmp which is explicitly allowed by _check_path_safety.
    except Exception:
        pass
    head_budget = int(max_chars * head_ratio)
    tail_budget = max_chars - head_budget
    head = output[:head_budget]
    tail = output[-tail_budget:]
    total = len(output)
    omitted = total - max_chars
    meta = f"\n\n... ({omitted:,} of {total:,} chars omitted, showing first {head_budget:,} + last {tail_budget:,}) ...\n"
    if spill_path:
        meta += f"Full output saved to {spill_path} — use the read tool with offset/limit to inspect specific sections.\n"
    meta += "IMPORTANT: The command has finished. Analyze the output above and continue with your next action.\n"
    return head + meta + tail


# ── Handlers ────────────────────────────────────────────────────────────


async def _bash_handler(
    args: dict[str, Any], session: Any = None, **_kw
) -> tuple[str, bool]:
    command = args.get("command", "")
    if not command:
        return "No command provided.", False
    if len(command) > MAX_COMMAND_LENGTH:
        return (
            f"Command too long ({len(command)} chars, max {MAX_COMMAND_LENGTH}). "
            f"Write the command to a script file and execute that instead."
        ), False
    is_dangerous, reason = _check_dangerous_command(command)
    if is_dangerous:
        import os

        # 1. Parse env whitelist
        whitelist_raw = os.environ.get("AIDD_INTERN_DANGEROUS_COMMANDS_WHITELIST", "")
        whitelist = [item.strip() for item in whitelist_raw.split(",") if item.strip()]

        # 2. Parse session config whitelist
        if session and getattr(session, "config", None):
            session_whitelist = getattr(
                session.config, "dangerous_commands_whitelist", []
            )
            if session_whitelist:
                whitelist.extend(session_whitelist)

        # 3. Whitelist check
        is_whitelisted = False
        for item in whitelist:
            if item in command:
                is_whitelisted = True
                break

        if is_whitelisted:
            logger.info(f"Dangerous command bypassed by whitelist: {command}")
        else:
            # 4. Interactive Console Confirmation (Claude Code style)
            import sys

            if sys.stdin.isatty():
                print(
                    f"\n⚠️  WARNING: Potentially dangerous command detected ({reason})."
                )
                print(f"Command: {command}")
                try:
                    sys.stdout.flush()
                    response = (
                        input("Are you sure you want to run this? (y/N): ")
                        .strip()
                        .lower()
                    )
                    if response in ("y", "yes"):
                        logger.info(
                            "Dangerous command approved by user via interactive console."
                        )
                    else:
                        return (
                            f"❌ Execution blocked: Potentially dangerous command ({reason}) "
                            f"was rejected by the user.",
                            False,
                        )
                except Exception as e:
                    return (
                        f"❌ Execution blocked: Failed to get user approval in console: {e}",
                        False,
                    )
            else:
                # 5. Non-interactive fallback block
                return (
                    f"❌ Execution blocked: Potentially dangerous command detected ({reason}). "
                    f"Execution was blocked because the terminal is non-interactive. "
                    f"To run this command, configure it in your whitelist via "
                    f"AIDD_INTERN_DANGEROUS_COMMANDS_WHITELIST environment variable or config.json.",
                    False,
                )
    command = wrap_shell_command_with_hub_artifact_bootstrap(command, session)
    work_dir = args.get("work_dir", ".")

    # Also validate path safety of work_dir
    is_safe_dir, dir_err = _check_path_safety(work_dir)
    if not is_safe_dir:
        return dir_err, False

    timeout = min(args.get("timeout") or DEFAULT_TIMEOUT, MAX_TIMEOUT)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=timeout,
        )
        output = _strip_ansi(result.stdout + result.stderr)
        output = _truncate_output(output)
        if not output.strip():
            output = "(no output)"
        return output, result.returncode == 0
    except subprocess.TimeoutExpired:
        return (
            f"Command timed out after {timeout}s and was killed.\n\n"
            f"For long-running commands, run in the background and poll:\n"
            f"  nohup <command> > /tmp/output.log 2>&1 & echo $!\n"
            f"Then check status with:\n"
            f"  kill -0 <PID> 2>/dev/null && echo 'running' || echo 'done'\n"
            f"  tail -n 50 /tmp/output.log"
        ), False
    except Exception as e:
        return f"bash error: {e}", False


async def _read_handler(args: dict[str, Any], **_kw) -> tuple[str, bool]:
    file_path = args.get("path", "")
    if not file_path:
        return "No path provided.", False

    # Path safety validation
    is_safe, err_msg = _check_path_safety(file_path)
    if not is_safe:
        return err_msg, False

    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}", False
    if p.is_dir():
        return "Cannot read a directory. Use bash with 'ls' instead.", False
    try:
        raw_content = p.read_text()
    except Exception as e:
        return f"read error: {e}", False

    _files_read.add(_resolve_path(file_path))

    lines = raw_content.splitlines()
    offset = max((args.get("offset") or 1), 1)
    limit = args.get("limit") or DEFAULT_READ_LINES

    selected = lines[offset - 1 : offset - 1 + limit]
    numbered = []
    for i, line in enumerate(selected, start=offset):
        if len(line) > MAX_LINE_LENGTH:
            line = line[:MAX_LINE_LENGTH] + "..."
        numbered.append(f"{i:>6}\t{line}")

    return "\n".join(numbered), True


async def _write_handler(args: dict[str, Any], **_kw) -> tuple[str, bool]:
    file_path = args.get("path", "")
    content = args.get("content", "")
    if not file_path:
        return "No path provided.", False

    # Path safety validation
    is_safe, err_msg = _check_path_safety(file_path)
    if not is_safe:
        return err_msg, False

    p = Path(file_path)
    if p.exists() and _resolve_path(file_path) not in _files_read:
        return (
            f"You must read {file_path} before overwriting it. "
            f"Use the read tool first to see current contents."
        ), False
    try:
        _atomic_write(p, content)
        _files_read.add(_resolve_path(file_path))
        msg = f"Wrote {len(content)} bytes to {file_path}"
        # Syntax validation for Python files
        if p.suffix == ".py":
            from agent.tools.edit_utils import validate_python

            warnings = validate_python(content, file_path)
            if warnings:
                msg += "\n\nValidation warnings:\n" + "\n".join(
                    f"  ⚠ {w}" for w in warnings
                )
        return msg, True
    except Exception as e:
        return f"write error: {e}", False


async def _edit_handler(args: dict[str, Any], **_kw) -> tuple[str, bool]:
    from agent.tools.edit_utils import apply_edit, validate_python

    file_path = args.get("path", "")
    old_str = args.get("old_str", "")
    new_str = args.get("new_str", "")
    replace_all = args.get("replace_all", False)
    mode = args.get("mode", "replace")

    if not file_path:
        return "No path provided.", False

    # Path safety validation
    is_safe, err_msg = _check_path_safety(file_path)
    if not is_safe:
        return err_msg, False

    if old_str == new_str:
        return "old_str and new_str must differ.", False

    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}", False
    if _resolve_path(file_path) not in _files_read:
        return (
            f"You must read {file_path} before editing it. "
            f"Use the read tool first to see current contents."
        ), False

    try:
        text = p.read_text()
    except Exception as e:
        return f"edit read error: {e}", False

    try:
        new_text, replacements, fuzzy_note = apply_edit(
            text, old_str, new_str, mode=mode, replace_all=replace_all
        )
    except ValueError as e:
        return str(e), False

    try:
        _atomic_write(p, new_text)
    except Exception as e:
        return f"edit write error: {e}", False

    msg = f"Edited {file_path} ({replacements} replacement{'s' if replacements > 1 else ''})"
    if fuzzy_note:
        msg += f" {fuzzy_note}"
    # Syntax validation for Python files
    if p.suffix == ".py":
        warnings = validate_python(new_text, file_path)
        if warnings:
            msg += "\n\nValidation warnings:\n" + "\n".join(
                f"  ⚠ {w}" for w in warnings
            )
    return msg, True


# ── Local tool specs (override sandbox /app references) ────────────────

_LOCAL_TOOL_SPECS = {
    "bash": {
        "description": (
            "Run a shell command on the local machine and return stdout/stderr.\n"
            "\n"
            "IMPORTANT: Do NOT use bash for file operations — use the dedicated tools instead:\n"
            "- To read files: use read (not cat/head/tail)\n"
            "- To edit files: use edit (not sed/awk)\n"
            "- To write files: use write (not echo/cat <<EOF)\n"
            "\n"
            "Commands run in a shell at the working directory. Each invocation is independent.\n"
            "Chain dependent commands with &&. Independent commands should be "
            "separate bash calls (they can run in parallel).\n"
            "\n"
            "For long-running commands (training, evaluation), run in the background and poll:\n"
            "  nohup <command> > /tmp/output.log 2>&1 & echo $!\n"
            "Then check status:\n"
            "  kill -0 <PID> 2>/dev/null && echo 'running' || echo 'done'\n"
            "  tail -n 50 /tmp/output.log\n"
            "\n"
            "Timeout default 120s, max 36000s."
        ),
        "parameters": {
            "type": "object",
            "required": ["command"],
            "additionalProperties": False,
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "description": {
                    "type": "string",
                    "description": "Short description (5-10 words, active voice).",
                },
                "work_dir": {
                    "type": "string",
                    "description": "Working directory (default: current directory).",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional timeout in seconds (default: 120, max: 36000).",
                },
            },
        },
    },
    "read": {
        "description": (
            "Reads a file from the local filesystem. Returns contents with line numbers "
            "(cat -n format).\n"
            "\n"
            "Usage:\n"
            "- By default, reads up to 2000 lines from the beginning of the file.\n"
            "- You can optionally specify offset and limit for large files, but prefer "
            "reading the whole file first.\n"
            "- Lines longer than 4000 chars are truncated.\n"
            "- Cannot read directories — use bash with 'ls' instead.\n"
            "- You should read multiple potentially useful files in parallel when possible.\n"
            "- IMPORTANT: Always read a file before editing or overwriting it. The edit and "
            "write tools will reject operations on files you haven't read."
        ),
        "parameters": {
            "type": "object",
            "required": ["path"],
            "additionalProperties": False,
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "The line number to start reading from (1-based). Only provide if the file is too large to read at once.",
                },
                "limit": {
                    "type": "integer",
                    "description": "The number of lines to read. Only provide if the file is too large to read at once.",
                },
            },
        },
    },
    "write": {
        "description": (
            "Writes a file to the local filesystem. Overwrites the existing file if one "
            "exists at the path.\n"
            "\n"
            "- If this is an existing file, you MUST use the read tool first. This tool "
            "will fail if you did not read the file first.\n"
            "- ALWAYS prefer editing existing files with the edit tool over overwriting "
            "with write.\n"
            "- Creates parent directories as needed."
        ),
        "parameters": {
            "type": "object",
            "required": ["path", "content"],
            "additionalProperties": False,
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "The complete file content to write.",
                },
            },
        },
    },
    "edit": {
        "description": (
            "Performs string replacements in files. Supports exact matching with "
            "fuzzy fallback.\n"
            "\n"
            "Usage:\n"
            "- You must read the file at least once before editing. This tool will "
            "error if you attempt an edit without reading the file.\n"
            "- The edit will FAIL if old_str is not unique in the file. Either provide "
            "a larger string with more surrounding context to make it unique, or set "
            "replace_all to true.\n"
            "- old_str and new_str must differ.\n"
            "- Preserve indentation exactly as it appears in the file.\n"
            "- Do NOT include line number prefixes from read output in old_str or new_str.\n"
            "- To delete code, set new_str to empty string.\n"
            "- Use replace_all for renaming variables or strings across the file.\n"
            "\n"
            "Modes:\n"
            "- replace (default): replace first occurrence of old_str with new_str.\n"
            "- append_after: insert new_str immediately after old_str (old_str is kept).\n"
            "- prepend_before: insert new_str immediately before old_str (old_str is kept)."
        ),
        "parameters": {
            "type": "object",
            "required": ["path", "old_str", "new_str"],
            "additionalProperties": False,
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit.",
                },
                "old_str": {
                    "type": "string",
                    "description": "The text to find in the file. Must match exactly (fuzzy matching is used as fallback).",
                },
                "new_str": {
                    "type": "string",
                    "description": "The replacement text. For append_after/prepend_before modes, the text to insert.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences of old_str (default: false).",
                    "default": False,
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "append_after", "prepend_before"],
                    "description": "Edit mode (default: replace).",
                    "default": "replace",
                },
            },
        },
    },
}

_HANDLERS = {
    "bash": _bash_handler,
    "read": _read_handler,
    "write": _write_handler,
    "edit": _edit_handler,
}


def get_local_tools():
    """Return local ToolSpecs for bash/read/write/edit (no sandbox_create)."""
    from agent.core.tools import ToolSpec

    tools = []
    for name, spec in _LOCAL_TOOL_SPECS.items():
        handler = _HANDLERS.get(name)
        if handler is None:
            continue
        tools.append(
            ToolSpec(
                name=name,
                description=spec["description"],
                parameters=spec["parameters"],
                handler=handler,
            )
        )
    return tools
