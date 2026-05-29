"""Python wrapper that re-exports the native Rust extension.

Maturin places the compiled ``_native`` shared library inside this package.
All public symbols are re-exported so callers can continue to use::

    from aidd_intern_core import save_json_atomic
"""

try:
    from ._native import *  # noqa: F401,F403
    from ._native import (  # noqa: F401  (explicit re-exports for IDE support)
        save_json_atomic,
        normalize_and_hash_args,
        scrub_string,
        scrub_obj,
        json_dumps_sorted,
        json_canonical_bytes,
        read_file_utf8,
        clip_ansi_string,
        visible_width,
        detect_doom_loop_rust,
        format_layered_memories_rust,
        search_wiki_entries_rust,
        search_skills_rust,
        is_binder_design_session_rust,
    )

    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
