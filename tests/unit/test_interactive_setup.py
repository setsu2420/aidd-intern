from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.utils.cli_ops import (
    maybe_interactive_update,
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


def test_maybe_interactive_update_disabled(monkeypatch):
    import sys

    # Disable by env variable
    monkeypatch.setenv("AIDD_INTERN_DISABLE_UPDATE_CHECK", "1")

    # Mock sys.stdout.isatty to True to test env check first
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    # We should return early and not raise any exceptions
    maybe_interactive_update()


def test_maybe_interactive_update_non_tty(monkeypatch):
    import sys

    # Mock sys.stdout.isatty to False
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

    # We should return early and not raise any exceptions
    maybe_interactive_update()


def test_maybe_interactive_update_is_current(monkeypatch):
    import sys

    # Mock sys.stdout.isatty to True
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    # Mock version check result as current
    from agent.core.version_check import VersionCheckResult

    mock_result = VersionCheckResult(
        status="current",
        source="origin/main",
        detail="matches",
    )
    monkeypatch.setattr(
        "agent.core.version_check.check_for_update",
        lambda *args, **kwargs: mock_result,
    )

    # Should skip update without prompting or exit
    maybe_interactive_update()


def test_maybe_interactive_update_outdated_declined(monkeypatch):
    import sys

    # Mock sys.stdout.isatty to True
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    # Mock outdated version check
    from agent.core.version_check import VersionCheckResult

    mock_result = VersionCheckResult(
        status="outdated",
        source="origin/main",
        detail="behind",
        current="123456789",
        latest="987654321",
    )
    monkeypatch.setattr(
        "agent.core.version_check.check_for_update",
        lambda *args, **kwargs: mock_result,
    )

    # Mock user input "n" to decline update
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    # Should print message and continue without exit
    maybe_interactive_update()


def test_maybe_interactive_update_outdated_accepted(monkeypatch):
    import sys

    # Mock sys.stdout.isatty to True
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    # Mock outdated version check
    from agent.core.version_check import VersionCheckResult

    mock_result = VersionCheckResult(
        status="outdated",
        source="origin/main",
        detail="behind",
        current="123456789",
        latest="987654321",
    )
    monkeypatch.setattr(
        "agent.core.version_check.check_for_update",
        lambda *args, **kwargs: mock_result,
    )

    # Mock user input "y" to accept update
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    # Mock run_update returning 0
    monkeypatch.setattr("agent.utils.cli_ops.run_update", lambda *args, **kwargs: 0)

    # Should trigger sys.exit(0)
    with pytest.raises(SystemExit) as excinfo:
        maybe_interactive_update()
    assert excinfo.value.code == 0
