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
