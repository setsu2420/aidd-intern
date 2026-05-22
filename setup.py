"""Build configuration with optional Rust native extension.

When a Rust toolchain (rustc + cargo) is available, setuptools-rust will
compile the PyO3-based ``aidd_intern_core._native`` extension and the
package gains GIL-free acceleration on JSON serialization, secret
redaction, and ANSI string processing.

When no Rust toolchain is detected the build silently falls back to
pure-Python implementations so ``pip install -e .`` / ``uv sync``
always succeeds without any extra setup.

Usage:
    pip install -e .          # auto-detect Rust, fallback if missing
    pip install -e ".[dev]"   # same, plus dev extras

To force a release-optimised Rust build for maximum performance::

    maturin develop --release        # requires maturin in dev deps
    # or equivalently:
    scripts/setup-rust.sh
"""

from setuptools import setup

try:
    from setuptools_rust import Binding, RustExtension
except ImportError:
    # setuptools-rust not installed — skip Rust extension entirely.
    RustExtension = None  # type: ignore[assignment,misc]
    Binding = None  # type: ignore[assignment,misc]


def _get_rust_extensions():
    """Return Rust extensions list; empty if setuptools-rust is missing."""
    if RustExtension is None:
        return []
    return [
        RustExtension(
            target="aidd_intern_core._native",
            path="Cargo.toml",
            binding=Binding.PyO3,
            py_limited_api=False,
            optional=True,  # Silently skip when rustc/cargo is absent
        ),
    ]


setup(
    rust_extensions=_get_rust_extensions(),
    # Let setuptools handle zip-safe detection; we have a native .so
    zip_safe=False,
)
