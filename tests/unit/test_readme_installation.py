from __future__ import annotations

import json
import subprocess
from io import StringIO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_REPO_URL = "https://github.com/setsu2420/aidd-intern"
PUBLIC_CLONE_URL = f"{PUBLIC_REPO_URL}.git"
LEGACY_REPO_URL = "https://github.com/huggingface/aidd-intern"
LEGACY_SSH_CLONE_URL = "git@github.com:huggingface/aidd-intern.git"
README_FILES = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "README.zh-CN.md",
    PROJECT_ROOT / "README.ja.md",
]
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
UPDATE_SCRIPT = PROJECT_ROOT / "scripts" / "update-local.sh"
DOCTOR_MODULE = PROJECT_ROOT / "agent" / "core" / "doctor.py"
AIDD_PREPARE_MODULE = PROJECT_ROOT / "agent" / "tools" / "aidd_prepare_tool.py"


def test_readme_quick_start_uses_public_https_clone_url():
    install_sequence = (
        f"git clone {PUBLIC_CLONE_URL}\n"
        "cd aidd-intern\n"
        "uv sync --extra dev\n"
        "uv tool install -e ."
    )

    for readme_path in README_FILES:
        print(f"STEP 1: Reading {readme_path.relative_to(PROJECT_ROOT)}")
        text = readme_path.read_text(encoding="utf-8")

        clone_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("git clone ")
        ]
        print(f"STEP 2: clone lines = {clone_lines}")
        assert clone_lines == [f"git clone {PUBLIC_CLONE_URL}"]

        print("STEP 3: Checking install commands stay in the project directory")
        assert install_sequence in text

        print("STEP 4: Checking the old SSH-only clone command is absent")
        assert LEGACY_SSH_CLONE_URL not in text

        print("STEP 5: Checking the README explains why uv runs after cd")
        assert "pyproject.toml" in text


def test_public_repository_links_are_aligned():
    paths = [
        *README_FILES,
        PROJECT_ROOT / "package.json",
        PROJECT_ROOT / "agent" / "core" / "hub_artifacts.py",
        PROJECT_ROOT / "agent" / "core" / "session_uploader.py",
    ]

    for path in paths:
        print(f"STEP 1: Checking source URL in {path.relative_to(PROJECT_ROOT)}")
        text = path.read_text(encoding="utf-8")
        assert PUBLIC_REPO_URL in text
        assert LEGACY_REPO_URL not in text

    print("STEP 2: Checking package metadata repository URL")
    package_json = json.loads((PROJECT_ROOT / "package.json").read_text())
    assert package_json["repository"]["url"] == PUBLIC_REPO_URL

    print("STEP 3: Checking backlog tooling default GitHub repo")
    backlog_script = (PROJECT_ROOT / "scripts" / "prioritize_backlog.py").read_text(
        encoding="utf-8"
    )
    assert 'DEFAULT_GITHUB_REPO = "setsu2420/aidd-intern"' in backlog_script


def test_english_readme_documents_local_update_and_env_setup():
    print("STEP 1: Reading README.md")
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    print("STEP 2: Checking first-time install copies the env template")
    assert "cp .env.example .env" in text

    print("STEP 3: Checking local updates use the non-destructive script")
    assert "## Local Updates" in text
    assert "scripts/update-local.sh" in text
    assert "npm install -g aidd-intern@latest" in text
    assert "aidd-intern update --dry-run" in text
    assert "npm run update:local" in text
    assert "git pull --ff-only origin <current-branch>" in text
    assert "scripts/update-local.sh --with-frontend" in text

    print("STEP 4: Checking the post-install doctor command is documented")
    assert "aidd-intern --doctor" in text

    print("STEP 5: Checking LLM API key setup is model-specific")
    expected_pairs = {
        "openrouter/openai/gpt-5.2": "OPENROUTER_API_KEY",
        "openai/gpt-5.5": "OPENAI_API_KEY",
        "anthropic/claude-opus-4-6": "ANTHROPIC_API_KEY",
        "siliconflow/deepseek-ai/DeepSeek-V4-Flash": "SILICONFLOW_API_KEY",
    }
    for model_id, env_var in expected_pairs.items():
        assert model_id in text
        assert env_var in text

    print("STEP 6: Checking npm LLM configuration guide is documented")
    assert "aidd-intern configure-llm openrouter" in text
    assert "aidd-intern configure-llm local" in text


def test_readmes_document_aidd_preparation_stage():
    expected_terms = {
        "README.md": [
            "## AIDD Preparation Stage",
            "Literature research",
            "PDB download",
            "Structure cropping",
            "Hotspot residue determination",
        ],
        "README.zh-CN.md": [
            "## AIDD 准备阶段",
            "文献资料调研",
            "PDB 文件获取下载",
            "结构剪裁",
            "热点残基确定",
        ],
        "README.ja.md": [
            "## AIDD 準備段階",
            "文献調査",
            "PDB 取得",
            "構造 crop",
            "Hotspot residue 決定",
        ],
    }

    for filename, terms in expected_terms.items():
        print(f"STEP 1: Reading {filename}")
        text = (PROJECT_ROOT / filename).read_text(encoding="utf-8")

        print("STEP 2: Checking the complete preparation command is documented")
        assert "aidd-intern --prepare-aidd" in text
        assert "--target-name" in text
        assert "--pdb-id" in text
        assert "--target-chains" in text
        assert "--partner-chains" in text
        assert "--residue-ranges" in text

        print("STEP 3: Checking all four preparation stages are named")
        for term in terms:
            assert term in text

        print("STEP 4: Checking preparation artifacts are documented")
        assert "aidd_preparation_manifest.json" in text
        assert "literature/literature_sources.md" in text
        assert "structures/raw/<PDB_ID>.pdb" in text
        assert "analysis/hotspots.json" in text

        print("STEP 5: Checking contact-derived hotspot caveat is documented")
        assert "aidd_prepare" in text
        assert (
            "experimental binding-energy proof" in text
            or "实验结合能证明" in text
            or "実験的 binding energy" in text
        )


def test_localized_readmes_document_env_template_update_and_doctor():
    expected = {
        "README.zh-CN.md": "## 本地更新",
        "README.ja.md": "## ローカル更新",
    }

    for filename, update_heading in expected.items():
        print(f"STEP 1: Reading {filename}")
        text = (PROJECT_ROOT / filename).read_text(encoding="utf-8")

        print("STEP 2: Checking env template setup is documented")
        assert "cp .env.example .env" in text

        print("STEP 3: Checking local update workflow is documented")
        assert update_heading in text
        assert "scripts/update-local.sh" in text
        assert "npm install -g aidd-intern@latest" in text
        assert "aidd-intern update --dry-run" in text
        assert "npm run update:local" in text
        assert "scripts/update-local.sh --with-frontend" in text

        print("STEP 4: Checking doctor command is documented")
        assert "aidd-intern --doctor" in text

        print("STEP 5: Checking npm LLM configuration guide is documented")
        assert "aidd-intern configure-llm openrouter" in text
        assert "aidd-intern configure-llm local" in text


def test_env_example_has_real_configuration_keys_without_token_values():
    print("STEP 1: Reading .env.example")
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    required_keys = [
        "AIDD_INTERN_DEFAULT_MODEL_ID",
        "AIDD_INTERN_MODELS_CONFIG",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "SILICONFLOW_API_KEY",
        "GOOGLE_SEARCH_API_KEY",
        "GOOGLE_SEARCH_ENGINE_ID",
        "GOOGLE_API_KEY",
        "GOOGLE_CSE_ID",
        "HF_TOKEN",
        "GITHUB_TOKEN",
        "LOCAL_LLM_BASE_URL",
        "LOCAL_LLM_API_KEY",
        "AIDD_INTERN_ENABLE_PROTEINMCP",
        "AIDD_INTERN_DISABLE_UPDATE_CHECK",
    ]

    for key in required_keys:
        print(f"STEP 2: Checking {key} is present")
        assert f"{key}=" in text

    print("STEP 3: Checking no real-looking secrets are committed")
    forbidden_fragments = ["sk-", "hf_", "ghp_", "github_pat_"]
    for fragment in forbidden_fragments:
        assert fragment not in text


def test_update_script_is_non_destructive_and_prints_steps():
    print("STEP 1: Reading scripts/update-local.sh")
    text = UPDATE_SCRIPT.read_text(encoding="utf-8")

    print("STEP 2: Checking the update uses fast-forward-only git pull")
    assert 'git pull --ff-only "$remote" "$branch"' in text

    print("STEP 3: Checking dependency and CLI refresh commands")
    assert "uv sync --extra dev" in text
    assert "uv tool install -e ." in text
    assert "npm ci" in text

    print("STEP 4: Checking the script prints diagnostic steps")
    for step in range(1, 6):
        assert f"STEP {step}:" in text

    print("STEP 5: Checking destructive git commands are absent")
    forbidden_commands = [
        "git reset",
        "git checkout --",
        "git clean",
        "git push",
    ]
    for command in forbidden_commands:
        assert command not in text


def test_update_script_help_runs_without_side_effects():
    print("STEP 1: Running update script help command")
    result = subprocess.run(
        ["bash", str(UPDATE_SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    print(f"STEP 2: stdout = {result.stdout.strip()}")
    assert "Usage: scripts/update-local.sh [--with-frontend]" in result.stdout

    print("STEP 3: Checking help documents remote, branch, and frontend options")
    assert "AIDD_INTERN_UPDATE_REMOTE" in result.stdout
    assert "AIDD_INTERN_UPDATE_BRANCH" in result.stdout
    assert "--with-frontend" in result.stdout

    print("STEP 4: Checking help does not emit errors")
    assert result.stderr == ""


def test_package_json_exposes_npm_local_update_scripts():
    print("STEP 1: Reading package.json")
    package_json = json.loads((PROJECT_ROOT / "package.json").read_text())

    print("STEP 2: Checking npm source checkout update scripts")
    scripts = package_json["scripts"]
    assert scripts["update:local"] == "bash scripts/update-local.sh"
    assert scripts["update:local:frontend"] == (
        "bash scripts/update-local.sh --with-frontend"
    )
    assert scripts["update:npm:dry-run"] == "node src/cli.ts update --dry-run"


def test_doctor_module_documents_each_diagnostic_step():
    print("STEP 1: Reading agent/core/doctor.py")
    text = DOCTOR_MODULE.read_text(encoding="utf-8")

    expected_steps = [
        "Checking Python runtime",
        "Checking required commands",
        "Loading AIDD-Intern config",
        "Checking selected LLM provider",
        "Checking Google Search configuration",
        "Checking AIDD-Intern version",
        "Checking local update helper",
        "Checking optional frontend dependencies",
        "Checking optional ProteinMCP setting",
    ]

    for step in expected_steps:
        print(f"STEP 2: Checking doctor step text: {step}")
        assert step in text

    print("STEP 3: Checking doctor does not execute update or install commands")
    forbidden_invocations = [
        '["git", "pull"',
        '["uv", "sync"',
        '["uv", "tool", "install"',
        '["npm", "ci"',
    ]
    for invocation in forbidden_invocations:
        assert invocation not in text


def test_aidd_prepare_module_documents_real_preparation_operations():
    print("STEP 1: Reading agent/tools/aidd_prepare_tool.py")
    text = AIDD_PREPARE_MODULE.read_text(encoding="utf-8")

    print("STEP 2: Checking preparation operations are implemented")
    for operation in [
        "literature_research",
        "download_pdb",
        "crop_structure",
        "identify_hotspots",
        "run_preparation",
    ]:
        assert f'"{operation}"' in text

    print("STEP 3: Checking RCSB download endpoint and PDB contact cutoff")
    assert "https://files.rcsb.org/download" in text
    assert "DEFAULT_HOTSPOT_CUTOFF = 4.5" in text

    print("STEP 4: Checking the CLI helper prints visible steps")
    for step in [
        "Creating AIDD preparation project",
        "Searching literature metadata",
        "Downloading PDB coordinates from RCSB",
        "Cropping target structure",
        "Determining candidate hotspot residues",
    ]:
        assert step in text


def test_doctor_command_prints_step_by_step_output():
    print("STEP 1: Importing the doctor runner")
    from agent.core.doctor import run_doctor

    print("STEP 2: Running doctor against the current checkout")
    output = StringIO()
    exit_code = run_doctor(output=output)
    rendered = output.getvalue()

    print(f"STEP 3: doctor exit code = {exit_code}")
    assert exit_code in {0, 1}

    print("STEP 4: Checking every diagnostic step is visible")
    for step in range(1, 9):
        assert f"STEP {step}:" in rendered

    print("STEP 5: Checking the summary is visible for debugging")
    assert "Doctor summary:" in rendered
    assert "Result:" in rendered
