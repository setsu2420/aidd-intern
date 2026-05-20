from __future__ import annotations

import json
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
