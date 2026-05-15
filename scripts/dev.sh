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
backend_dir="$repo_root/backend"
frontend_dir="$repo_root/frontend"

backend_host="${AIDD_INTERN_BACKEND_HOST:-::1}"
backend_port="${AIDD_INTERN_BACKEND_PORT:-7860}"
frontend_host="${AIDD_INTERN_FRONTEND_HOST:-localhost}"
frontend_port="${AIDD_INTERN_FRONTEND_PORT:-5173}"

backend_pid=""
frontend_pid=""

cleanup() {
  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill "$frontend_pid" 2>/dev/null || true
  fi
  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
  fi
  wait "$frontend_pid" "$backend_pid" 2>/dev/null || true
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "error: $command_name is required but was not found in PATH" >&2
    exit 1
  fi
}

trap cleanup EXIT INT TERM

require_command uv
require_command npm

if [[ ! -d "$frontend_dir/node_modules" ]]; then
  echo "frontend dependencies are missing; running npm ci..."
  (cd "$frontend_dir" && npm ci)
fi

echo "starting backend on [$backend_host]:$backend_port..."
(
  cd "$backend_dir"
  uv run python -m uvicorn main:app --host "$backend_host" --port "$backend_port"
) &
backend_pid=$!

echo "starting frontend on $frontend_host:$frontend_port..."
(
  cd "$frontend_dir"
  npm run dev -- --host "$frontend_host" --port "$frontend_port"
) &
frontend_pid=$!

cat <<EOF

AIDD-Intern local dev is starting.
Frontend: http://localhost:$frontend_port/
Backend health check: curl -g http://[::1]:$backend_port/api

Press Ctrl+C to stop both services.

EOF

set +e
wait -n "$backend_pid" "$frontend_pid"
exit_code=$?
set -e
exit "$exit_code"
