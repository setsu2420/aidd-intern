"""CLI operations for aidd-intern: update, configure-llm, etc."""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_update(
    *,
    check: bool = False,
    dry_run: bool = False,
    with_frontend: bool = False,
) -> int:
    """Update the local checkout using scripts/update-local.sh."""
    script = PROJECT_ROOT / "scripts" / "update-local.sh"

    if not script.exists():
        print(f"error: {script} not found. Are you running from a source checkout?")
        return 1

    if check:
        # Version check is already performed by _maybe_print_update_notice
        # in agent/main.py. We can just run the doctor to show the status.
        from agent.core.doctor import run_doctor

        return run_doctor()

    cmd = [str(script)]
    if with_frontend:
        cmd.append("--with-frontend")

    if dry_run:
        print(f"Dry run: would execute {' '.join(cmd)}")
        return 0

    try:
        # Use inherit for stdout/stderr so the user sees progress
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\nUpdate interrupted.")
        return 130
    except Exception as e:
        print(f"error: update failed: {e}")
        return 1


PROVIDER_GUIDES = {
    "openrouter": {
        "name": "OpenRouter",
        "models": ["openrouter/openai/gpt-5.2"],
        "requiredEnv": ["OPENROUTER_API_KEY"],
        "notes": [
            "Set AIDD_INTERN_DEFAULT_MODEL_ID to an openrouter/<provider>/<model> id."
        ],
    },
    "openai": {
        "name": "OpenAI",
        "models": ["openai/gpt-5.5"],
        "requiredEnv": ["OPENAI_API_KEY"],
        "notes": [
            "Use direct openai/<model> ids when you want OpenAI as the provider."
        ],
    },
    "anthropic": {
        "name": "Anthropic",
        "models": ["anthropic/claude-opus-4-6"],
        "requiredEnv": ["ANTHROPIC_API_KEY"],
        "notes": [
            "Use direct anthropic/<model> ids when you want Anthropic as the provider."
        ],
    },
    "siliconflow": {
        "name": "SiliconFlow",
        "models": ["siliconflow/deepseek-ai/DeepSeek-V4-Flash"],
        "requiredEnv": ["SILICONFLOW_API_KEY"],
        "notes": [
            "Use siliconflow/<model> ids for the SiliconFlow OpenAI-compatible endpoint."
        ],
    },
    "local": {
        "name": "Local OpenAI-compatible server",
        "models": [
            "ollama/llama3.1:8b",
            "vllm/Qwen/Qwen3-Coder-30B-A3B-Instruct",
            "lm_studio/google/gemma-3-4b",
            "llamacpp/qwen3.6-35b-a3b-gguf",
        ],
        "requiredEnv": ["AIDD_INTERN_DEFAULT_MODEL_ID"],
        "optionalEnv": [
            "LOCAL_LLM_BASE_URL",
            "LOCAL_LLM_API_KEY",
            "OLLAMA_BASE_URL",
            "VLLM_BASE_URL",
            "LMSTUDIO_BASE_URL",
            "LLAMACPP_BASE_URL",
        ],
        "notes": [
            "Start the local inference server first; AIDD-Intern does not load model weights itself."
        ],
    },
}


def run_configure_llm(provider: str | None = None) -> int:
    """Print provider-specific LLM environment setup steps."""
    normalized = provider.strip().lower() if provider else None
    guide = PROVIDER_GUIDES.get(normalized) if normalized else None

    if normalized and not guide:
        print(f"error: unknown provider: {provider}")
        print(f"Known providers: {', '.join(PROVIDER_GUIDES.keys())}")
        return 1

    if guide:
        _print_guide(guide)
        return 0

    print("STEP 1: Choose one provider and model id")
    for entry in PROVIDER_GUIDES.values():
        print(f"- {entry['name']}: {entry['models'][0]}")
    print("")
    print("STEP 2: Add the matching environment variables to .env")
    print("Run a provider-specific guide, for example:")
    print("  aidd-intern configure-llm openrouter")
    print("  aidd-intern configure-llm local")
    print("")
    print("STEP 3: Verify the runtime side with the Python CLI")
    print("  aidd-intern --doctor")
    print('  aidd-intern --model openrouter/openai/gpt-5.2 "hello"')
    return 0


def _print_guide(guide: dict) -> None:
    print(f"STEP 1: Configure {guide['name']}")
    print("Model examples:")
    for model in guide["models"]:
        print(f"  {model}")
    print("")
    print("STEP 2: Set environment variables in .env")
    for env_name in guide["requiredEnv"]:
        print(f"  {env_name}=...")
    if guide.get("optionalEnv"):
        print("Optional:")
        for env_name in guide["optionalEnv"]:
            print(f"  {env_name}=...")
    print("")
    print("STEP 3: Verify")
    print(f"  AIDD_INTERN_DEFAULT_MODEL_ID={guide['models'][0]}")
    print("  aidd-intern --doctor")
    for note in guide["notes"]:
        print(f"Note: {note}")


def needs_interactive_setup(args) -> bool:
    """Determine if we should prompt the user with interactive LLM setup during first run."""
    import os

    # 1. Skip setup for administrative commands
    if args.prompt_or_command in {"doctor", "update", "configure-llm"}:
        return False
    if getattr(args, "doctor", False):
        return False

    # 2. Check if a model is explicitly passed via CLI argument
    if getattr(args, "model", None):
        return False

    # 3. Check if standard LLM configs are already present in env or .env
    dotenv_path = PROJECT_ROOT / ".env"
    common_keys = [
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SILICONFLOW_API_KEY",
        "LOCAL_LLM_API_KEY",
    ]

    has_env_key = any(os.environ.get(k) for k in common_keys)
    has_env_model = bool(os.environ.get("AIDD_INTERN_DEFAULT_MODEL_ID"))

    has_dotenv_key = False
    has_dotenv_model = False
    if dotenv_path.exists():
        from dotenv import dotenv_values

        try:
            values = dotenv_values(dotenv_path)
            has_dotenv_key = any(values.get(k) for k in common_keys)
            has_dotenv_model = bool(values.get("AIDD_INTERN_DEFAULT_MODEL_ID"))
        except Exception:
            pass

    # If any model configuration exists, we do NOT trigger first-run interactive helper
    if has_env_key or has_dotenv_key or has_env_model or has_dotenv_model:
        return False

    return True


def run_interactive_first_run_setup() -> None:
    """Guide first-time users through choosing a model and setting API keys, then write to .env."""
    from dotenv import load_dotenv

    print("=" * 65)
    print("🌟 Welcome to AIDD-Intern Drug Design Assistant! 🌟")
    print("=" * 65)
    print("We detected that you haven't configured any default LLM models or API keys.")
    print(
        "The agent requires an LLM to automatically analyze targets, identify hotspots,"
    )
    print("generate macromolecular binders, and learn from reflection loops.")
    print("-" * 65)

    print("Step 1: Choose your LLM Provider")
    print(
        "  [1] OpenRouter  - Recommended: Aggregates global SOTA models, extremely stable"
    )
    print(
        "  [2] SiliconFlow - Recommended: Low latency & cost-efficient, stable endpoint for DeepSeek"
    )
    print("  [3] OpenAI      - Directly use official GPT-4o / gpt-4o-mini models")
    print("  [4] Anthropic   - Directly use official Claude 3.5 Sonnet / Haiku")
    print("  [5] Local/Custom - Use local models via Ollama, vLLM, or custom servers")
    print("")

    choice = ""
    while choice not in {"1", "2", "3", "4", "5"}:
        try:
            choice = input("Select your provider (1-5, default 1): ").strip()
            if choice == "":
                choice = "1"
        except (KeyboardInterrupt, EOFError):
            print(
                "\nSetup interrupted. To configure manually, edit the `.env` file in the project root."
            )
            return

    # Provider specs mapping
    provider_map = {
        "1": {
            "name": "OpenRouter",
            "default_model": "openrouter/openai/gpt-5.2",
            "api_key_name": "OPENROUTER_API_KEY",
            "prompt_msg": "Enter your OpenRouter API Key (sk-or-v1-...): ",
            "note": "(Tip: You can obtain your key at https://openrouter.ai)",
        },
        "2": {
            "name": "SiliconFlow",
            "default_model": "siliconflow/deepseek-ai/DeepSeek-V4-Flash",
            "api_key_name": "SILICONFLOW_API_KEY",
            "prompt_msg": "Enter your SiliconFlow API Key (sk-...): ",
            "note": "(Tip: You can obtain your key at https://siliconflow.cn)",
        },
        "3": {
            "name": "OpenAI",
            "default_model": "openai/gpt-4o",
            "api_key_name": "OPENAI_API_KEY",
            "prompt_msg": "Enter your OpenAI API Key (sk-...): ",
            "note": "(Tip: You can obtain your key at https://platform.openai.com)",
        },
        "4": {
            "name": "Anthropic",
            "default_model": "anthropic/claude-3.5-sonnet",
            "api_key_name": "ANTHROPIC_API_KEY",
            "prompt_msg": "Enter your Anthropic API Key (sk-ant-...): ",
            "note": "(Tip: You can obtain your key at https://console.anthropic.com)",
        },
        "5": {
            "name": "Local (Ollama/vLLM)",
            "default_model": "ollama/llama3.1:8b",
            "api_key_name": "LOCAL_LLM_API_KEY",
            "prompt_msg": "Enter your local/custom API Key (or press Enter if none): ",
            "note": "(Tip: Specify your local model ID; endpoint URL can be configured in .env later)",
        },
    }

    provider_info = provider_map[choice]
    print(f"\nYou have selected provider: {provider_info['name']}")
    print("-" * 65)

    # Choose model
    print("Step 2: Configure your default Model ID")
    print(f"Recommended default model: [ {provider_info['default_model']} ]")
    try:
        model_id = input(
            "Enter Model ID (press Enter to use recommended default): "
        ).strip()
        if not model_id:
            model_id = provider_info["default_model"]
    except (KeyboardInterrupt, EOFError):
        print("\nSetup interrupted.")
        return

    # Input API Key
    print(f"\nStep 3: Configure your API Key {provider_info['note']}")
    api_key = ""
    while not api_key:
        try:
            api_key = input(provider_info["prompt_msg"]).strip()
            if choice == "5" and not api_key:
                api_key = "local-no-key"
                break
        except (KeyboardInterrupt, EOFError):
            print("\nSetup interrupted.")
            return

    # Optional HF Token
    print("\nStep 4: Configure Hugging Face Token [Optional]")
    print(
        "Some biological MCP tools may require an HF_TOKEN for authentication when downloading weights."
    )
    try:
        hf_token = input(
            "Enter your HF_TOKEN (hf_..., or press Enter to skip): "
        ).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nSetup interrupted.")
        return

    # Write back merged environment settings to project root .env
    dotenv_path = PROJECT_ROOT / ".env"
    existing_lines = []
    if dotenv_path.exists():
        existing_lines = dotenv_path.read_text(encoding="utf-8").splitlines()

    new_config = {
        "AIDD_INTERN_DEFAULT_MODEL_ID": model_id,
        provider_info["api_key_name"]: api_key,
    }
    if hf_token:
        new_config["HF_TOKEN"] = hf_token

    updated_keys = set()
    final_lines = []

    for line in existing_lines:
        line_strip = line.strip()
        if not line_strip or line_strip.startswith("#"):
            final_lines.append(line)
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            if key in new_config:
                final_lines.append(f"{key}={new_config[key]}")
                updated_keys.add(key)
            else:
                final_lines.append(line)
        else:
            final_lines.append(line)

    for key, value in new_config.items():
        if key not in updated_keys:
            final_lines.append(f"{key}={value}")

    try:
        dotenv_path.write_text("\n".join(final_lines) + "\n", encoding="utf-8")
        print("\n" + "=" * 65)
        print("🎉 Configuration Saved Successfully! 🎉")
        print(
            "Your LLM credentials have been written to the `.env` file in the project root:"
        )
        print(f"  - Default Model ID: {model_id}")
        print(f"  - API Key Written: {provider_info['api_key_name']}")
        if hf_token:
            print("  - HF Token Written: HF_TOKEN")
        print("-" * 65)
        print(
            "Environment reloaded successfully! The agent is launching the macromolecular design loop now...\n"
        )

        load_dotenv(dotenv_path, override=True)
    except Exception as e:
        print(f"\nerror: Failed to write to `.env` file: {e}")


def maybe_interactive_update() -> None:
    """Check for update at CLI startup. If outdated and stdout is a TTY, prompt to update instantly."""
    import sys
    import os
    from agent.core.version_check import check_for_update

    # Check if disabled
    if os.environ.get("AIDD_INTERN_DISABLE_UPDATE_CHECK") in ("1", "true", "TRUE"):
        return

    # Check if it's an interactive TTY session
    if not sys.stdout.isatty():
        return

    try:
        # Check for update with a 3.0s timeout so we do not block user startup in bad network conditions
        result = check_for_update(timeout=3.0)
    except Exception:
        # Silently ignore checks failure (e.g. offline or no git)
        return

    if result.status != "outdated":
        return

    # Get short SHAs for neat display
    curr_sha = result.current[:7] if result.current else "unknown"
    late_sha = result.latest[:7] if result.latest else "unknown"

    # Color definitions for interactive shell beauty
    CYAN = "\033[1;36m"
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RESET = "\033[0m"

    print(f"\n{CYAN}" + "=" * 65 + f"{RESET}")
    print(f"{GREEN}🎉 A new version of AIDD-Intern is available!{RESET}")
    print(f"{CYAN}" + "-" * 65 + f"{RESET}")
    print(f"  - Current Version: {YELLOW}{curr_sha}{RESET}")
    print(f"  - Latest Version:  {GREEN}{late_sha}{RESET} (via {result.source})")
    print(
        "  - Update includes the latest binder design workflows & performance optimizations."
    )
    print(f"{CYAN}" + "=" * 65 + f"{RESET}")

    try:
        choice = (
            input(
                "Would you like to automatically pull and update the project now? (y/N): "
            )
            .strip()
            .lower()
        )
        if choice in ("y", "yes"):
            print(
                f"\n{YELLOW}Starting automatic update. This may take a few moments...{RESET}"
            )
            code = run_update(with_frontend=False)
            if code == 0:
                print(f"\n{CYAN}" + "=" * 65 + f"{RESET}")
                print(
                    f"{GREEN}🎉 System updated successfully to the latest version!{RESET}"
                )
                print(
                    "Please restart `aidd-intern` to experience the new macromolecular design features."
                )
                print(f"{CYAN}" + "=" * 65 + f"{RESET}\n")
                sys.exit(0)
            else:
                print(
                    f"\n{YELLOW}warning: The update script returned a non-zero exit code ({code}). Update might be incomplete.{RESET}"
                )
                print("💡 Troubleshooting suggestions:")
                print(
                    "  1. If you have local changes, run `git stash` first to prevent merge conflicts."
                )
                print(
                    "  2. You can also try upgrading manually later by running `scripts/update-local.sh`.\n"
                )
        else:
            print("Skipping automatic update. Continuing startup...\n")
    except (KeyboardInterrupt, EOFError):
        print("\nUpdate cancelled. Continuing startup...\n")
