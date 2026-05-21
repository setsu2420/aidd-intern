"""Local installation diagnostics for AIDD-Intern."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TextIO

from agent.core.local_models import (
    LOCAL_MODEL_BASE_URL_ENV,
    LOCAL_MODEL_PREFIXES,
    local_model_provider,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LLM_PROVIDER_KEYS = {
    "openai/": "OPENAI_API_KEY",
    "anthropic/": "ANTHROPIC_API_KEY",
    "openrouter/": "OPENROUTER_API_KEY",
    "siliconflow/": "SILICONFLOW_API_KEY",
}


CheckStatus = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class DoctorCheck:
    status: CheckStatus
    name: str
    detail: str
    fix: str | None = None


def run_doctor(*, output: TextIO | None = None) -> int:
    """Run diagnostics and return a shell exit code.

    The doctor is intentionally read-only. It checks local files, commands,
    environment variables, config parseability, and the remote Git revision, but
    it does not install, fetch, start servers, or call mutating APIs.
    """
    stream = output or sys.stdout
    checks: list[DoctorCheck] = []

    _print_step(stream, 1, "Checking Python runtime")
    checks.append(_check_python())

    _print_step(stream, 2, "Checking required commands")
    checks.extend(_check_commands())

    _print_step(stream, 3, "Loading AIDD-Intern config")
    config_check, model_name = _check_config()
    checks.append(config_check)

    _print_step(stream, 4, "Checking selected LLM provider")
    checks.append(_check_llm_provider(model_name))

    _print_step(stream, 5, "Checking Google Search configuration")
    checks.append(_check_google_search())

    _print_step(stream, 6, "Checking AIDD-Intern version")
    checks.append(_check_version())

    _print_step(stream, 7, "Checking local update helper")
    checks.append(_check_update_helper())

    _print_step(stream, 8, "Checking optional frontend dependencies")
    checks.append(_check_frontend_dependencies())

    _print_step(stream, 9, "Checking optional ProteinMCP setting")
    checks.append(_check_proteinmcp_setting())

    print("\nDoctor summary:", file=stream)
    for check in checks:
        print(_format_check(check), file=stream)
        if check.fix:
            print(f"       fix: {check.fix}", file=stream)

    failures = [check for check in checks if check.status == "fail"]
    warnings = [check for check in checks if check.status == "warn"]
    print(
        f"\nResult: {len(failures)} fail, {len(warnings)} warn, "
        f"{len(checks) - len(failures) - len(warnings)} ok",
        file=stream,
    )
    return 1 if failures else 0


def _print_step(stream: TextIO, number: int, message: str) -> None:
    print(f"STEP {number}: {message}", file=stream)


def _format_check(check: DoctorCheck) -> str:
    label = {
        "ok": "OK",
        "warn": "WARN",
        "fail": "FAIL",
    }[check.status]
    return f"  [{label}] {check.name}: {check.detail}"


def _check_python() -> DoctorCheck:
    version = platform.python_version()
    if sys.version_info < (3, 11):
        return DoctorCheck(
            "fail",
            "python",
            f"Python {version} is too old",
            "Install Python 3.11+ or run through uv.",
        )
    return DoctorCheck("ok", "python", f"Python {version}")


def _check_commands() -> list[DoctorCheck]:
    checks = [
        _command_check("git", required=True),
        _command_check("uv", required=True),
        _command_check("npm", required=False),
    ]
    return checks


def _command_check(command: str, *, required: bool) -> DoctorCheck:
    path = shutil.which(command)
    if path is None:
        status: CheckStatus = "fail" if required else "warn"
        detail = "not found in PATH"
        fix = f"Install {command} and reopen your shell."
        if command == "npm":
            fix = "Install Node.js 22+ only if you work on the frontend or npm harness."
        return DoctorCheck(status, command, detail, fix)

    version = _command_version(command)
    detail = f"{path}"
    if version:
        detail = f"{detail} ({version})"
    return DoctorCheck("ok", command, detail)


def _command_version(command: str) -> str | None:
    try:
        result = subprocess.run(
            [command, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if output else None


def _check_config() -> tuple[DoctorCheck, str | None]:
    try:
        from agent.config import load_config

        config = load_config(str(PROJECT_ROOT / "configs" / "cli_agent_config.json"))
    except Exception as exc:
        return (
            DoctorCheck(
                "fail",
                "config",
                f"could not load CLI config: {exc}",
                "Run from a complete checkout and verify configs/cli_agent_config.json.",
            ),
            None,
        )

    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return (
            DoctorCheck(
                "warn",
                "config",
                f"loaded model {config.model_name!r}, but .env is missing",
                "Copy .env.example to .env and set the provider keys you use.",
            ),
            config.model_name,
        )

    return (
        DoctorCheck("ok", "config", f"loaded model {config.model_name!r}"),
        config.model_name,
    )


def _check_llm_provider(model_name: str | None) -> DoctorCheck:
    if not model_name:
        return DoctorCheck(
            "fail",
            "llm",
            "no model configured",
            "Set AIDD_INTERN_DEFAULT_MODEL_ID or update configs/models.json.",
        )

    if model_name.startswith(LOCAL_MODEL_PREFIXES):
        provider = local_model_provider(model_name)
        base_env = (
            provider["base_url_env"]
            if provider is not None
            else LOCAL_MODEL_BASE_URL_ENV
        )
        base_url = os.environ.get(base_env) or os.environ.get(LOCAL_MODEL_BASE_URL_ENV)
        if base_url:
            return DoctorCheck(
                "ok",
                "llm",
                f"{model_name} uses local endpoint {base_url}",
            )
        return DoctorCheck(
            "warn",
            "llm",
            f"{model_name} is local, but no local endpoint env var is set",
            f"Start the local server or set {base_env}/{LOCAL_MODEL_BASE_URL_ENV}.",
        )

    for prefix, env_name in LLM_PROVIDER_KEYS.items():
        if model_name.startswith(prefix):
            if os.environ.get(env_name):
                return DoctorCheck("ok", "llm", f"{env_name} is set for {model_name}")
            return DoctorCheck(
                "warn",
                "llm",
                f"{env_name} is not set for {model_name}",
                f"Add {env_name}=... to .env or choose another --model.",
            )

    if os.environ.get("HF_TOKEN"):
        return DoctorCheck("ok", "llm", f"HF_TOKEN is set for {model_name}")
    return DoctorCheck(
        "warn",
        "llm",
        f"{model_name} likely uses Hugging Face Router, but HF_TOKEN is not set",
        "Set HF_TOKEN or choose an OpenAI/OpenRouter/SiliconFlow/local model.",
    )


def _check_google_search() -> DoctorCheck:
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY") or os.environ.get(
        "GOOGLE_API_KEY"
    )
    engine_id = os.environ.get("GOOGLE_SEARCH_ENGINE_ID") or os.environ.get(
        "GOOGLE_CSE_ID"
    )
    if api_key and engine_id:
        return DoctorCheck("ok", "google_search", "Google Search credentials are set")
    if api_key or engine_id:
        return DoctorCheck(
            "warn",
            "google_search",
            "Google Search is partially configured",
            "Set both GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID.",
        )
    return DoctorCheck(
        "warn",
        "google_search",
        "Google Search credentials are not set",
        "Set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID for real Google Search.",
    )


def _check_update_helper() -> DoctorCheck:
    script = PROJECT_ROOT / "scripts" / "update-local.sh"
    if not script.exists():
        return DoctorCheck(
            "fail",
            "update",
            "scripts/update-local.sh is missing",
            "Restore the checkout or pull the latest repository version.",
        )
    if not os.access(script, os.X_OK):
        return DoctorCheck(
            "warn",
            "update",
            "scripts/update-local.sh is not executable",
            "Run chmod +x scripts/update-local.sh.",
        )
    return DoctorCheck("ok", "update", "scripts/update-local.sh is executable")


def _check_version() -> DoctorCheck:
    from agent.core.version_check import check_for_update, format_update_notice

    result = check_for_update(PROJECT_ROOT)
    if result.status == "current":
        return DoctorCheck(
            "ok",
            "version",
            f"local checkout is current with {result.source}",
        )
    if result.status == "disabled":
        return DoctorCheck("ok", "version", result.detail)
    if result.status == "outdated":
        return DoctorCheck(
            "warn",
            "version",
            result.detail,
            format_update_notice(result),
        )
    return DoctorCheck(
        "warn",
        "version",
        result.detail,
        "Run scripts/update-local.sh from a source checkout when you want to update.",
    )


def _check_frontend_dependencies() -> DoctorCheck:
    package_json = PROJECT_ROOT / "frontend" / "package.json"
    node_modules = PROJECT_ROOT / "frontend" / "node_modules"
    if not package_json.exists():
        return DoctorCheck("ok", "frontend", "frontend package is not present")
    if node_modules.exists():
        return DoctorCheck("ok", "frontend", "frontend/node_modules exists")
    return DoctorCheck(
        "warn",
        "frontend",
        "frontend dependencies are not installed",
        "Run scripts/update-local.sh --with-frontend or cd frontend && npm ci.",
    )


def _check_proteinmcp_setting() -> DoctorCheck:
    enabled = os.environ.get("AIDD_INTERN_ENABLE_PROTEINMCP", "").strip()
    if enabled not in {"1", "true", "TRUE", "yes", "on"}:
        return DoctorCheck(
            "ok",
            "proteinmcp",
            "local ProteinMCP launchers are disabled by default",
        )
    launcher = PROJECT_ROOT / "scripts" / "run-proteinmcp-local.sh"
    if launcher.exists():
        return DoctorCheck(
            "ok",
            "proteinmcp",
            "local ProteinMCP is enabled and launcher script exists",
        )
    return DoctorCheck(
        "fail",
        "proteinmcp",
        "AIDD_INTERN_ENABLE_PROTEINMCP=1 but launcher script is missing",
        "Restore scripts/run-proteinmcp-local.sh or disable ProteinMCP.",
    )


if __name__ == "__main__":
    raise SystemExit(run_doctor())
