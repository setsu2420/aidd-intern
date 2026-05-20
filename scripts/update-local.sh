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
with_frontend=0

usage() {
  cat <<EOF
Usage: scripts/update-local.sh [--with-frontend]

Update a local AIDD-Intern checkout without overwriting local work.

Environment:
  AIDD_INTERN_UPDATE_REMOTE   Git remote to pull from (default: origin)
  AIDD_INTERN_UPDATE_BRANCH   Branch to pull (default: current branch)

Options:
  --with-frontend             Also run npm ci in frontend/
  -h, --help                  Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-frontend)
      with_frontend=1
      shift
      ;;
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
if [[ "$with_frontend" == "1" ]]; then
  require_command npm
fi

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

echo "STEP 3: Reinstalling the editable Python CLI"
uv tool install -e .

if [[ "$with_frontend" == "1" ]]; then
  echo "STEP 4: Syncing frontend dependencies"
  (cd "$repo_root/frontend" && npm ci)
else
  echo "STEP 4: Skipping frontend dependencies; pass --with-frontend to run npm ci"
fi

echo "STEP 5: Verifying the installed CLI is on PATH"
if ! command -v aidd-intern >/dev/null 2>&1; then
  echo "warning: aidd-intern is not on PATH after installation" >&2
  echo "hint: add uv's tool bin directory to PATH: uv tool dir --bin" >&2
else
  command -v aidd-intern
fi

echo "AIDD-Intern local checkout is up to date."
