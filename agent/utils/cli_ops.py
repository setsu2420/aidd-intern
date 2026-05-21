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
    print("🌟 欢迎首次使用 AIDD-Intern 智能药物设计助手！ 🌟")
    print("=" * 65)
    print("检测到您当前尚未配置任何大分子药物设计默认 LLM 大模型与 API 密钥。")
    print("智能体需要 LLM 才能自动分析靶点、识别热点、生成结合剂和反射学习。")
    print("-" * 65)

    print("第一步: 请选择您的 LLM 提供商 (LLM Provider)")
    print("  [1] OpenRouter  - 推荐：汇聚全球顶级推理模型，科研任务极其稳定")
    print("  [2] SiliconFlow - 推荐：国内低延迟、高性价比，最稳定的 DeepSeek 等通道")
    print("  [3] OpenAI      - 官方直接接入 GPT-4o / GPT-3.5 等原生模型")
    print("  [4] Anthropic   - 官方直接接入 Claude 3.5 Sonnet 等高级推理模型")
    print("  [5] 本地部署     - 兼容 OpenAI 的本地大模型 (如 Ollama, vLLM 等)")
    print("")

    choice = ""
    while choice not in {"1", "2", "3", "4", "5"}:
        try:
            choice = input("请选择提供商 (输入 1-5, 默认 1): ").strip()
            if choice == "":
                choice = "1"
        except (KeyboardInterrupt, EOFError):
            print(
                "\n配置已被中断。若需手动配置，请直接编辑项目根目录下的 `.env` 文件。"
            )
            return

    # Provider specs mapping
    provider_map = {
        "1": {
            "name": "OpenRouter",
            "default_model": "openrouter/openai/gpt-5.2",
            "api_key_name": "OPENROUTER_API_KEY",
            "prompt_msg": "请输入您的 OpenRouter API 密钥 (格式如 sk-or-v1-...): ",
            "note": "（提示：您可以在 https://openrouter.ai 获取密钥）",
        },
        "2": {
            "name": "SiliconFlow",
            "default_model": "siliconflow/deepseek-ai/DeepSeek-V4-Flash",
            "api_key_name": "SILICONFLOW_API_KEY",
            "prompt_msg": "请输入您的 SiliconFlow API 密钥 (格式如 sk-...): ",
            "note": "（提示：您可以在 https://siliconflow.cn 获取密钥）",
        },
        "3": {
            "name": "OpenAI",
            "default_model": "openai/gpt-4o",
            "api_key_name": "OPENAI_API_KEY",
            "prompt_msg": "请输入您的 OpenAI API 密钥 (格式如 sk-...): ",
            "note": "（提示：您可以在 https://platform.openai.com 获取密钥）",
        },
        "4": {
            "name": "Anthropic",
            "default_model": "anthropic/claude-3.5-sonnet",
            "api_key_name": "ANTHROPIC_API_KEY",
            "prompt_msg": "请输入您的 Anthropic API 密钥 (格式如 sk-ant-...): ",
            "note": "（提示：您可以在 https://console.anthropic.com 获取密钥）",
        },
        "5": {
            "name": "Local (Ollama/vLLM)",
            "default_model": "ollama/llama3.1:8b",
            "api_key_name": "LOCAL_LLM_API_KEY",
            "prompt_msg": "请输入您的本地 API 密钥 (若无密钥直接按回车): ",
            "note": "（提示：您可以在此指定本地 Model ID，本地端点 URL 可随后在 .env 里调整）",
        },
    }

    provider_info = provider_map[choice]
    print(f"\n您已选择提供商: {provider_info['name']}")
    print("-" * 65)

    # Choose model
    print("第二步: 请配置您想默认使用的 Model ID")
    print(f"系统推荐的默认模型: [ {provider_info['default_model']} ]")
    try:
        model_id = input("请输入 Model ID (直接按回车使用默认推荐): ").strip()
        if not model_id:
            model_id = provider_info["default_model"]
    except (KeyboardInterrupt, EOFError):
        print("\n配置已被中断。")
        return

    # Input API Key
    print(f"\n第三步: 请配置您的 API 密钥 {provider_info['note']}")
    api_key = ""
    while not api_key:
        try:
            api_key = input(provider_info["prompt_msg"]).strip()
            if choice == "5" and not api_key:
                api_key = "local-no-key"
                break
        except (KeyboardInterrupt, EOFError):
            print("\n配置已被中断。")
            return

    # Optional HF Token
    print("\n第四步: 配置 Hugging Face Token [可选]")
    print("部分的科学 MCP 工具在下载模型权重时可能需要 HF_TOKEN 进行授权。")
    try:
        hf_token = input(
            "请输入您的 HF_TOKEN (格式如 hf_...，不需要请直接回车跳过): "
        ).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n配置已被中断。")
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
        print("🎉 配置保存成功！🎉")
        print("您的专属 LLM 凭证已成功写入项目根目录下的 `.env` 文件：")
        print(f"  - 默认模型 ID: {model_id}")
        print(f"  - API 密钥已写入: {provider_info['api_key_name']}")
        if hf_token:
            print("  - HF 令牌已写入: HF_TOKEN")
        print("-" * 65)
        print("配置环境已成功重新加载！系统即刻自动拉起智能大分子设计服务...\n")

        load_dotenv(dotenv_path, override=True)
    except Exception as e:
        print(f"\nerror: 写入 `.env` 文件失败: {e}")
