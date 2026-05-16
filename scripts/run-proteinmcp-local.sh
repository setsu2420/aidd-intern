#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <bindcraft_mcp|boltzgen_mcp|pxdesign_mcp>" >&2
  exit 64
fi

server="$1"
base_dir="${AIDD_INTERN_PROTEINMCP_HOME:-${HOME}/.cache/aidd-intern/proteinmcp}"
auto_clone="${AIDD_INTERN_PROTEINMCP_AUTO_CLONE:-1}"
auto_setup="${AIDD_INTERN_PROTEINMCP_AUTO_SETUP:-0}"

case "$server" in
  bindcraft_mcp)
    repo_url="${AIDD_INTERN_BINDCRAFT_MCP_REPO:-https://github.com/MacromNex/bindcraft_mcp.git}"
    repo_dir="${AIDD_INTERN_BINDCRAFT_MCP_DIR:-${base_dir}/bindcraft_mcp}"
    python_bin="${AIDD_INTERN_BINDCRAFT_MCP_PYTHON:-${repo_dir}/env/bin/python}"
    server_py="${repo_dir}/src/bindcraft_mcp.py"
    default_setup_args=()
    setup_args_var="${AIDD_INTERN_BINDCRAFT_SETUP_ARGS:-}"
    pythonpath="${repo_dir}/src:${repo_dir}/clean_scripts${PYTHONPATH:+:${PYTHONPATH}}"
    ;;
  boltzgen_mcp)
    repo_url="${AIDD_INTERN_BOLTZGEN_MCP_REPO:-https://github.com/MacromNex/boltzgen_mcp.git}"
    repo_dir="${AIDD_INTERN_BOLTZGEN_MCP_DIR:-${base_dir}/boltzgen_mcp}"
    python_bin="${AIDD_INTERN_BOLTZGEN_MCP_PYTHON:-${repo_dir}/env/bin/python}"
    server_py="${repo_dir}/src/server.py"
    default_setup_args=(--skip-models)
    setup_args_var="${AIDD_INTERN_BOLTZGEN_SETUP_ARGS:-}"
    pythonpath="${repo_dir}/src${PYTHONPATH:+:${PYTHONPATH}}"
    ;;
  pxdesign_mcp)
    repo_url="${AIDD_INTERN_PXDESIGN_REPO:-https://github.com/bytedance/PXDesign.git}"
    repo_dir="${AIDD_INTERN_PXDESIGN_DIR:-${base_dir}/PXDesign}"
    server_py="${AIDD_INTERN_WORKDIR:-.}/scripts/pxdesign_mcp_server.py"
    default_setup_args=()
    setup_args_var="${AIDD_INTERN_PXDESIGN_SETUP_ARGS:-}"
    pythonpath="${repo_dir}${PYTHONPATH:+:${PYTHONPATH}}"
    if [[ -n "${AIDD_INTERN_PXDESIGN_MCP_PYTHON:-}" ]]; then
      python_bin="${AIDD_INTERN_PXDESIGN_MCP_PYTHON}"
    elif command -v uv >/dev/null 2>&1 && [[ -f "${AIDD_INTERN_WORKDIR:-.}/uv.lock" ]]; then
      python_bin="uv"
      default_setup_args=()
    elif [[ -x "${repo_dir}/env/bin/python" ]]; then
      python_bin="${repo_dir}/env/bin/python"
    else
      python_bin="$(command -v python3 || command -v python)"
    fi
    ;;
  *)
    echo "unknown ProteinMCP server: ${server}" >&2
    echo "expected one of: bindcraft_mcp, boltzgen_mcp, pxdesign_mcp" >&2
    exit 64
    ;;
esac

if [[ ! -d "$repo_dir/.git" ]]; then
  if [[ "$auto_clone" != "1" ]]; then
    echo "ProteinMCP repo missing: ${repo_dir}" >&2
    echo "Run: scripts/setup-proteinmcp-local.sh ${server}" >&2
    exit 66
  fi
  mkdir -p "$(dirname "$repo_dir")"
  git clone --depth 1 "$repo_url" "$repo_dir" >&2
fi

if [[ "$server" != "pxdesign_mcp" && ! -x "$python_bin" ]]; then
  if [[ "$auto_setup" == "1" ]]; then
    # shellcheck disable=SC2206
    extra_setup_args=($setup_args_var)
    (cd "$repo_dir" && bash quick_setup.sh "${default_setup_args[@]}" "${extra_setup_args[@]}") >&2
  else
    echo "ProteinMCP environment missing: ${python_bin}" >&2
    echo "Run: scripts/setup-proteinmcp-local.sh ${server}" >&2
    echo "Or set AIDD_INTERN_PROTEINMCP_AUTO_SETUP=1 to let this launcher run quick_setup.sh." >&2
    exit 69
  fi
fi

if [[ ! -f "$server_py" ]]; then
  echo "ProteinMCP server file missing: ${server_py}" >&2
  exit 66
fi

cd "$repo_dir"
export PYTHONPATH="$pythonpath"
export PXDESIGN_REPO_DIR="${PXDESIGN_REPO_DIR:-$repo_dir}"
if [[ "$server" == "pxdesign_mcp" && "$python_bin" == "uv" ]]; then
  cd "${AIDD_INTERN_WORKDIR:-.}"
  exec uv run python "$server_py"
fi
exec "$python_bin" "$server_py"
