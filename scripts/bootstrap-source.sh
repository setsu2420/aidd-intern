#!/usr/bin/env bash
set -Eeuo pipefail

repo_url="https://github.com/setsu2420/aidd-intern.git"
target_dir="aidd-intern"
ref="${AIDD_INTERN_BOOTSTRAP_REF:-main}"
install_runtime=1

usage() {
  cat <<EOF
Usage: scripts/bootstrap-source.sh [--dir DIR] [--ref REF] [--with-frontend] [--no-install]

Clone or download AIDD-Intern and install the editable Python CLI.

Options:
  --dir DIR         Target checkout directory (default: aidd-intern)
  --ref REF         Branch or tag to clone/download (default: main)
  --no-install      Only create the source checkout
  -h, --help        Show this help

Environment:
  AIDD_INTERN_BOOTSTRAP_REF          Default ref when --ref is omitted
  AIDD_INTERN_BOOTSTRAP_ARCHIVE_URL  Archive URL used if git clone fails
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      target_dir="${2:-}"
      if [[ -z "$target_dir" ]]; then
        echo "error: --dir requires a value" >&2
        exit 2
      fi
      shift 2
      ;;
    --ref)
      ref="${2:-}"
      if [[ -z "$ref" ]]; then
        echo "error: --ref requires a value" >&2
        exit 2
      fi
      shift 2
      ;;
    --no-install)
      install_runtime=0
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

download_archive() {
  local archive_url="$1"
  local archive_path="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -fL "$archive_url" -o "$archive_path"
    return
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -O "$archive_path" "$archive_url"
    return
  fi

  echo "error: git clone failed and neither curl nor wget is available" >&2
  exit 1
}

if [[ -e "$target_dir" ]]; then
  echo "error: target directory already exists: $target_dir" >&2
  exit 1
fi

if [[ "$install_runtime" == "1" ]]; then
  require_command uv
fi

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

checkout_dir="$tmp_dir/aidd-intern"
used_archive=0

echo "STEP 1: Creating source checkout"
if command -v git >/dev/null 2>&1; then
  if git -c http.version=HTTP/1.1 clone --depth 1 --branch "$ref" "$repo_url" "$checkout_dir"; then
    :
  else
    echo "warning: git clone failed; trying GitHub archive fallback" >&2
    used_archive=1
  fi
else
  echo "warning: git is not available; trying GitHub archive fallback" >&2
  used_archive=1
fi

if [[ "$used_archive" == "1" ]]; then
  require_command tar
  archive_url="${AIDD_INTERN_BOOTSTRAP_ARCHIVE_URL:-https://github.com/setsu2420/aidd-intern/archive/refs/heads/${ref}.tar.gz}"
  archive_path="$tmp_dir/aidd-intern.tar.gz"
  download_archive "$archive_url" "$archive_path"
  mkdir -p "$tmp_dir/archive"
  tar -xzf "$archive_path" -C "$tmp_dir/archive"
  checkout_dir="$(find "$tmp_dir/archive" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  if [[ -z "$checkout_dir" ]]; then
    echo "error: archive did not contain a source directory" >&2
    exit 1
  fi
fi

mkdir -p "$(dirname "$target_dir")"
mv "$checkout_dir" "$target_dir"

if [[ "$install_runtime" != "1" ]]; then
  echo "AIDD-Intern source checkout created at: $target_dir"
  exit 0
fi

cd "$target_dir"

echo "STEP 2: Syncing Python dependencies"
uv sync --extra dev

echo "STEP 3: Installing the editable Python CLI"
uv tool install -e .

echo "STEP 4: Creating .env from template if needed"
if [[ -f .env ]]; then
  echo ".env already exists; leaving it unchanged"
else
  cp .env.example .env
fi

echo "STEP 5: Verifying the installed CLI is on PATH"
if ! command -v aidd-intern >/dev/null 2>&1; then
  echo "warning: aidd-intern is not on PATH after installation" >&2
  echo "hint: add uv's tool bin directory to PATH: uv tool dir --bin" >&2
else
  command -v aidd-intern
fi

if [[ "$used_archive" == "1" ]]; then
  echo "Note: archive fallback has no .git metadata; rerun this bootstrap script to refresh it."
fi

echo "AIDD-Intern is installed. Edit $target_dir/.env before the first real LLM call."
