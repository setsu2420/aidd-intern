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
bin_dir="${1:-$HOME/.local/bin}"
launcher="$bin_dir/aidd-intern-dev"

mkdir -p "$bin_dir"

if [[ -e "$launcher" && ! -L "$launcher" ]]; then
  echo "error: $launcher already exists and is not a symlink" >&2
  exit 1
fi

ln -sfn "$repo_root/scripts/dev.sh" "$launcher"

echo "installed $launcher -> $repo_root/scripts/dev.sh"
if [[ ":$PATH:" != *":$bin_dir:"* ]]; then
  echo "add this to your shell profile if needed:"
  echo "export PATH=\"$bin_dir:\$PATH\""
fi
