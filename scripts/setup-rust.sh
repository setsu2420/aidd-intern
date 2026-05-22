#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# scripts/setup-rust.sh — One-click Rust toolchain setup + build
# ─────────────────────────────────────────────────────────────
#
# Installs the Rust toolchain (rustup) if it is not already
# present, then compiles the PyO3 native extension in release
# mode for maximum performance.
#
# Usage:
#   ./scripts/setup-rust.sh
#   ./scripts/setup-rust.sh --debug     # faster compile, slower runtime
#
# Environment variables:
#   RUST_TOOLCHAIN  Override the Rust toolchain to install (default: stable)
# ─────────────────────────────────────────────────────────────
set -Eeuo pipefail

# ── Resolve repository root ──────────────────────────────────
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

RUST_TOOLCHAIN="${RUST_TOOLCHAIN:-stable}"
BUILD_MODE="release"
if [[ "${1:-}" == "--debug" ]]; then
  BUILD_MODE="dev"
  shift
fi

echo "========================================"
echo " AIDD-Intern Rust Acceleration Setup"
echo "========================================"

# ── Step 1: Detect or install Rust ──────────────────────────
install_rust() {
  echo ""
  echo "Rust toolchain not found. Installing rustup ($RUST_TOOLCHAIN)..."
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain "$RUST_TOOLCHAIN" --profile minimal

  # Source cargo environment for the current session
  if [[ -f "$HOME/.cargo/env" ]]; then
    # shellcheck disable=SC1091
    . "$HOME/.cargo/env"
  fi

  if command -v rustc >/dev/null 2>&1; then
    echo "Rust installed successfully: $(rustc --version)"
  else
    echo "error: rustc still not found after rustup installation" >&2
    echo "hint: add \$HOME/.cargo/bin to your PATH and re-run this script" >&2
    exit 1
  fi
}

if command -v rustc >/dev/null 2>&1; then
  echo "Rust toolchain detected: $(rustc --version)"
elif [[ -f "$HOME/.cargo/bin/rustc" ]]; then
  echo "Rust found at \$HOME/.cargo/bin: $($HOME/.cargo/bin/rustc --version)"
  # shellcheck disable=SC1091
  [[ -f "$HOME/.cargo/env" ]] && . "$HOME/.cargo/env"
else
  install_rust
fi

echo "cargo: $(cargo --version)"

# ── Step 2: Compile the native extension ─────────────────────
echo ""
echo "Compiling aidd_intern_core native extension ($BUILD_MODE mode)..."
echo ""

cd "$repo_root"

# Unset CONDA_PREFIX to avoid venv/conda path conflicts during maturin build
unset CONDA_PREFIX || true

if [[ "$BUILD_MODE" == "release" ]]; then
  uv run --with maturin maturin develop --release
else
  uv run --with maturin maturin develop
fi

echo ""
echo "========================================"
echo " Rust acceleration enabled!"
echo " aidd_intern_core._native is now active."
echo "========================================"
echo ""
echo "Verify with:"
echo "  python -c 'from aidd_intern_core._native import json_dumps_sorted; print(json_dumps_sorted({\"a\":1}))'"
echo ""
