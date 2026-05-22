#!/usr/bin/env bash
set -Eeuo pipefail

source_path="${BASH_SOURCE[0]}"
while [ -L "$source_path" ]; do
  source_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
  source_path="$(readlink "$source_path")"
  if [[ "$source_path" != /* ]]; then
    source_path="$source_dir/$source_path"
  fi
done

script_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

remote="${AIDD_INTERN_UPDATE_REMOTE:-origin}"
branch="${AIDD_INTERN_UPDATE_BRANCH:-}"

usage() {
  cat <<EOF
Usage: scripts/update-local.sh

Update a local AIDD-Intern checkout without overwriting local work.

Environment:
  AIDD_INTERN_UPDATE_REMOTE   Git remote to pull from (default: origin)
  AIDD_INTERN_UPDATE_BRANCH   Branch to pull (default: current branch)

Options:
  -h, --help                  Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "error: $command_name is required but was not found in PATH" >&2
    exit 1
  fi
}

require_command git
require_command uv

cd "$repo_root"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: $repo_root is not a Git working tree" >&2
  exit 1
fi

if [[ -z "$branch" ]]; then
  branch="$(git branch --show-current)"
fi
if [[ -z "$branch" ]]; then
  echo "error: detached HEAD; set AIDD_INTERN_UPDATE_BRANCH explicitly" >&2
  exit 1
fi

echo "STEP 1: Pulling $remote/$branch with --ff-only"
git pull --ff-only "$remote" "$branch"

echo "STEP 2: Syncing Python dependencies"
uv sync --extra dev

echo "STEP 2.5: Compile High-Performance Rust Core (Optional Acceleration)"
CARGO_BIN=""
if command -v cargo >/dev/null 2>&1; then
  CARGO_BIN="cargo"
elif [[ -f "$HOME/.cargo/bin/cargo" ]]; then
  CARGO_BIN="$HOME/.cargo/bin/cargo"
fi

if [[ -n "$CARGO_BIN" ]]; then
  echo "Found Rust compiler. Compiling aidd_intern_core module..."
  if [[ -f "$HOME/.cargo/env" ]]; then
    . "$HOME/.cargo/env"
  fi
  if (
    cd "$repo_root"
    unset CONDA_PREFIX || true
    uv run --with maturin maturin develop
  ); then
    echo "aidd_intern_core successfully compiled and installed."
  else
    echo "warning: Failed to compile aidd_intern_core module. Continuing without Rust core acceleration." >&2
    echo "AIDD-Intern will safely fall back to the native Python engine." >&2
  fi
else
  echo "Rust compiler not found. Skipping optional high-performance Rust core acceleration compilation."
  echo "AIDD-Intern will safely fall back to the native Python engine."
fi

echo "STEP 3: Reinstalling the editable Python CLI"
uv tool install -e .

echo "STEP 4: Verifying the installed CLI is on PATH"
if ! command -v aidd-intern >/dev/null 2>&1; then
  echo "warning: aidd-intern is not on PATH after installation" >&2
  echo "hint: add uv's tool bin directory to PATH: uv tool dir --bin" >&2
else
  command -v aidd-intern
fi

echo "AIDD-Intern local checkout is up to date."
