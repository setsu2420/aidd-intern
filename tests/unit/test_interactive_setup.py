from __future__ import annotations

from types import SimpleNamespace

from agent.utils.cli_ops import (
    needs_interactive_setup,
    run_interactive_first_run_setup,
)


def test_needs_interactive_setup_blocks_admin_commands():
    # 1. doctor should skip interactive setup
    args_doctor = SimpleNamespace(prompt_or_command="doctor", doctor=True, model=None)
    assert needs_interactive_setup(args_doctor) is False

    # 2. update should skip interactive setup
    args_update = SimpleNamespace(prompt_or_command="update", doctor=False, model=None)
    assert needs_interactive_setup(args_update) is False

    # 3. configure-llm should skip interactive setup
    args_config = SimpleNamespace(
        prompt_or_command="configure-llm", doctor=False, model=None
    )
    assert needs_interactive_setup(args_config) is False


def test_needs_interactive_setup_blocks_explicit_model_flag():
    # If the user passes --model, skip interactive setup
    args = SimpleNamespace(
        prompt_or_command="explain protein folding", doctor=False, model="openai/gpt-4o"
    )
    assert needs_interactive_setup(args) is False


def test_needs_interactive_setup_detects_existing_env(monkeypatch):
    # If key exists in environment variables, skip setup
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-existing-key")
    args = SimpleNamespace(
        prompt_or_command="explain protein folding", doctor=False, model=None
    )
    assert needs_interactive_setup(args) is False


def test_needs_interactive_setup_detects_existing_dotenv(tmp_path, monkeypatch):
    # Point PROJECT_ROOT to a temporary path where a custom .env exists
    from agent.utils import cli_ops

    # Temporarily override PROJECT_ROOT in cli_ops module
    monkeypatch.setattr(cli_ops, "PROJECT_ROOT", tmp_path)

    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("OPENROUTER_API_KEY=sk-or-existing\n", encoding="utf-8")

    args = SimpleNamespace(
        prompt_or_command="explain protein folding", doctor=False, model=None
    )
    assert needs_interactive_setup(args) is False


def test_run_interactive_first_run_setup_writes_dotenv(tmp_path, monkeypatch):
    from agent.utils import cli_ops

    # Redirect .env output to a temporary path
    monkeypatch.setattr(cli_ops, "PROJECT_ROOT", tmp_path)
    dotenv_file = tmp_path / ".env"

    # Pre-populate some existing search keys to ensure merge behavior
    dotenv_file.write_text("GOOGLE_SEARCH_API_KEY=AIzaSyTest\n", encoding="utf-8")

    # Mock user input:
    # 1. Choose "2" for SiliconFlow
    # 2. Press Enter to use default SiliconFlow model
    # 3. Enter API Key: "sk-mock-siliconflow-api-key"
    # 4. Skip HF_TOKEN (Press Enter)
    inputs = ["2", "", "sk-mock-siliconflow-api-key", ""]
    input_iter = iter(inputs)

    def mock_input(prompt=""):
        return next(input_iter)

    monkeypatch.setattr("builtins.input", mock_input)

    # Run interactive setup
    run_interactive_first_run_setup()

    assert dotenv_file.exists()
    content = dotenv_file.read_text(encoding="utf-8")

    # 1. Assert pre-existing keys are preserved
    assert "GOOGLE_SEARCH_API_KEY=AIzaSyTest" in content
    # 2. Assert selected model is written
    assert (
        "AIDD_INTERN_DEFAULT_MODEL_ID=siliconflow/deepseek-ai/DeepSeek-V4-Flash"
        in content
    )
    # 3. Assert provider-specific API key is written
    assert "SILICONFLOW_API_KEY=sk-mock-siliconflow-api-key" in content
