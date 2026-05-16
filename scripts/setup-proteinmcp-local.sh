#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat >&2 <<'EOF'
usage: scripts/setup-proteinmcp-local.sh [all|bindcraft_mcp|boltzgen_mcp|pxdesign_mcp]

Environment:
  AIDD_INTERN_PROTEINMCP_HOME       Base install dir. Default: ~/.cache/aidd-intern/proteinmcp
  AIDD_INTERN_BINDCRAFT_SETUP_ARGS  Extra args passed to bindcraft_mcp/quick_setup.sh
  AIDD_INTERN_BOLTZGEN_SETUP_ARGS   Extra args passed to boltzgen_mcp/quick_setup.sh
  AIDD_INTERN_PXDESIGN_SETUP_ARGS   Extra args passed to PXDesign/install.sh

Notes:
  - This script never uses Docker.
  - BoltzGen setup defaults to --skip-models so it does not block on a model
    download prompt. Download models later with the boltzgen MCP or CLI.
  - PXDesign setup uses the official Conda install script and never uses Docker.
EOF
}

target="${1:-all}"
base_dir="${AIDD_INTERN_PROTEINMCP_HOME:-${HOME}/.cache/aidd-intern/proteinmcp}"

clone_or_update() {
  local repo_url="$1"
  local repo_dir="$2"

  if [[ -d "$repo_dir/.git" ]]; then
    git -C "$repo_dir" pull --ff-only
  else
    mkdir -p "$(dirname "$repo_dir")"
    git clone --depth 1 "$repo_url" "$repo_dir"
  fi
}

setup_bindcraft() {
  local repo_dir="${AIDD_INTERN_BINDCRAFT_MCP_DIR:-${base_dir}/bindcraft_mcp}"
  clone_or_update "${AIDD_INTERN_BINDCRAFT_MCP_REPO:-https://github.com/MacromNex/bindcraft_mcp.git}" "$repo_dir"
  # shellcheck disable=SC2206
  local extra_args=(${AIDD_INTERN_BINDCRAFT_SETUP_ARGS:-})
  (cd "$repo_dir" && bash quick_setup.sh "${extra_args[@]}")
}

setup_boltzgen() {
  local repo_dir="${AIDD_INTERN_BOLTZGEN_MCP_DIR:-${base_dir}/boltzgen_mcp}"
  clone_or_update "${AIDD_INTERN_BOLTZGEN_MCP_REPO:-https://github.com/MacromNex/boltzgen_mcp.git}" "$repo_dir"
  # shellcheck disable=SC2206
  local extra_args=(${AIDD_INTERN_BOLTZGEN_SETUP_ARGS:---skip-models})
  (cd "$repo_dir" && bash quick_setup.sh "${extra_args[@]}")
}

setup_pxdesign() {
  local repo_dir="${AIDD_INTERN_PXDESIGN_DIR:-${base_dir}/PXDesign}"
  clone_or_update "${AIDD_INTERN_PXDESIGN_REPO:-https://github.com/bytedance/PXDesign.git}" "$repo_dir"

  if [[ ! -f "$repo_dir/install.sh" ]]; then
    echo "PXDesign install.sh not found in ${repo_dir}" >&2
    exit 66
  fi

  # shellcheck disable=SC2206
  local extra_args=(${AIDD_INTERN_PXDESIGN_SETUP_ARGS:-})
  if [[ ${#extra_args[@]} -eq 0 ]]; then
    extra_args=(--pkg_manager mamba --env_name pxdesign)
  fi
  (cd "$repo_dir" && bash install.sh "${extra_args[@]}")
}

case "$target" in
  all)
    setup_bindcraft
    setup_boltzgen
    setup_pxdesign
    ;;
  bindcraft_mcp)
    setup_bindcraft
    ;;
  boltzgen_mcp)
    setup_boltzgen
    ;;
  pxdesign_mcp)
    setup_pxdesign
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 64
    ;;
esac
