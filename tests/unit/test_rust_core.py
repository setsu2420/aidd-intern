"""Comprehensive tests for the aidd_intern_core Rust extension module.

Covers all 9 exported functions plus Python-fallback equivalence and
performance benchmarks.
"""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
try:
    import aidd_intern_core

    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False


skip_no_rust = pytest.mark.skipif(
    not RUST_AVAILABLE, reason="aidd_intern_core Rust module is not compiled"
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. save_json_atomic
# ═══════════════════════════════════════════════════════════════════════════


@skip_no_rust
def test_save_json_atomic_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "out.json")
        payload = json.dumps({"hello": "world"}).encode()
        aidd_intern_core.save_json_atomic(path, payload)
        assert json.loads(Path(path).read_text()) == {"hello": "world"}


@skip_no_rust
def test_save_json_atomic_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "a", "b", "c.json")
        aidd_intern_core.save_json_atomic(path, b"{}")
        assert Path(path).read_text() == "{}"


@skip_no_rust
def test_save_json_atomic_invalid_path():
    with pytest.raises(Exception):
        aidd_intern_core.save_json_atomic("/nonexistent_dir_xyz/test.json", b"data")


# ═══════════════════════════════════════════════════════════════════════════
# 2. normalize_and_hash_args
# ═══════════════════════════════════════════════════════════════════════════


@skip_no_rust
def test_hash_args_empty():
    result = aidd_intern_core.normalize_and_hash_args("")
    # MD5 of empty string, first 12 hex chars
    expected = hashlib.md5(b"").hexdigest()[:12]
    assert result == expected


@skip_no_rust
def test_hash_args_json_sorted():
    """Keys should be sorted before hashing, so different key orders match."""
    h1 = aidd_intern_core.normalize_and_hash_args('{"b":2,"a":1}')
    h2 = aidd_intern_core.normalize_and_hash_args('{"a":1,"b":2}')
    assert h1 == h2
    assert len(h1) == 12


@skip_no_rust
def test_hash_args_invalid_json_fallback():
    """Non-JSON input should still produce a 12-char hash."""
    result = aidd_intern_core.normalize_and_hash_args("not-json-at-all")
    assert len(result) == 12
    expected = hashlib.md5(b"not-json-at-all").hexdigest()[:12]
    assert result == expected


@skip_no_rust
def test_hash_args_nested():
    raw = json.dumps({"z": [3, 2, 1], "a": {"c": 1, "b": 2}})
    result = aidd_intern_core.normalize_and_hash_args(raw)
    assert len(result) == 12


# ═══════════════════════════════════════════════════════════════════════════
# 3. scrub_string
# ═══════════════════════════════════════════════════════════════════════════


@skip_no_rust
def test_scrub_string_hf_token():
    token = "hf_" + "A" * 30
    out = aidd_intern_core.scrub_string(f"key={token}")
    assert "[REDACTED_HF_TOKEN]" in out
    assert token not in out


@skip_no_rust
def test_scrub_string_anthropic():
    token = "sk-ant-" + "X" * 30
    out = aidd_intern_core.scrub_string(token)
    assert "[REDACTED_ANTHROPIC_KEY]" in out


@skip_no_rust
def test_scrub_string_openai():
    token = "sk-" + "A" * 50
    out = aidd_intern_core.scrub_string(token)
    assert "[REDACTED_OPENAI_KEY]" in out


@skip_no_rust
def test_scrub_string_github_classic():
    token = "ghp_" + "A" * 36
    out = aidd_intern_core.scrub_string(token)
    assert "[REDACTED_GITHUB_TOKEN]" in out


@skip_no_rust
def test_scrub_string_github_fine_grained():
    token = "github_pat_" + "A" * 36
    out = aidd_intern_core.scrub_string(token)
    assert "[REDACTED_GITHUB_TOKEN]" in out


@skip_no_rust
def test_scrub_string_aws_key():
    key = "AKIA" + "A" * 16
    out = aidd_intern_core.scrub_string(f"aws_key={key}")
    assert "[REDACTED_AWS_KEY_ID]" in out


@skip_no_rust
def test_scrub_string_bearer():
    out = aidd_intern_core.scrub_string("Authorization: Bearer " + "A" * 30)
    assert "Bearer [REDACTED]" in out


@skip_no_rust
def test_scrub_string_secret_env():
    out = aidd_intern_core.scrub_string("OPENAI_API_KEY=sk-abc123secret")
    assert "OPENAI_API_KEY=[REDACTED]" in out


@skip_no_rust
def test_scrub_string_no_match():
    text = "Hello, this is a normal message."
    assert aidd_intern_core.scrub_string(text) == text


@skip_no_rust
def test_scrub_string_empty():
    assert aidd_intern_core.scrub_string("") == ""


# ═══════════════════════════════════════════════════════════════════════════
# 4. scrub_obj
# ═══════════════════════════════════════════════════════════════════════════


@skip_no_rust
def test_scrub_obj_dict():
    token = "hf_" + "B" * 30
    obj = {"msg": f"token={token}", "count": 42}
    result = aidd_intern_core.scrub_obj(obj)
    assert "[REDACTED_HF_TOKEN]" in result["msg"]
    assert result["count"] == 42
    # Original must not be mutated
    assert token in obj["msg"]


@skip_no_rust
def test_scrub_obj_nested():
    token = "sk-ant-" + "C" * 30
    obj = {"level1": {"level2": [f"key: {token}", 3.14]}}
    result = aidd_intern_core.scrub_obj(obj)
    assert "[REDACTED_ANTHROPIC_KEY]" in result["level1"]["level2"][0]
    assert result["level1"]["level2"][1] == 3.14


@skip_no_rust
def test_scrub_obj_list():
    token = "ghp_" + "D" * 36
    result = aidd_intern_core.scrub_obj([f"tok={token}", "safe"])
    assert "[REDACTED_GITHUB_TOKEN]" in result[0]
    assert result[1] == "safe"


@skip_no_rust
def test_scrub_obj_none_passthrough():
    assert aidd_intern_core.scrub_obj(None) is None


@skip_no_rust
def test_scrub_obj_int_passthrough():
    assert aidd_intern_core.scrub_obj(123) == 123


# ═══════════════════════════════════════════════════════════════════════════
# 5. json_dumps_sorted
# ═══════════════════════════════════════════════════════════════════════════


@skip_no_rust
def test_json_dumps_sorted_keys():
    obj = {"z": 1, "a": 2, "m": 3}
    out = aidd_intern_core.json_dumps_sorted(obj)
    parsed = json.loads(out)
    assert list(parsed.keys()) == ["a", "m", "z"]


@skip_no_rust
def test_json_dumps_sorted_nested():
    obj = {"b": {"d": 4, "c": 3}, "a": 1}
    out = aidd_intern_core.json_dumps_sorted(obj)
    parsed = json.loads(out)
    assert list(parsed.keys()) == ["a", "b"]
    assert list(parsed["b"].keys()) == ["c", "d"]


@skip_no_rust
def test_json_dumps_sorted_unicode():
    """Non-ASCII characters should be preserved (ensure_ascii=False)."""
    obj = {"name": "蛋白质设计", "emoji": "🧬"}
    out = aidd_intern_core.json_dumps_sorted(obj)
    assert "蛋白质设计" in out
    assert "🧬" in out


@skip_no_rust
def test_json_dumps_sorted_types():
    obj = {"s": "hello", "i": 42, "f": 3.14, "b": True, "n": None}
    out = aidd_intern_core.json_dumps_sorted(obj)
    parsed = json.loads(out)
    assert parsed["s"] == "hello"
    assert parsed["i"] == 42
    assert abs(parsed["f"] - 3.14) < 1e-9
    assert parsed["b"] is True
    assert parsed["n"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 6. json_canonical_bytes
# ═══════════════════════════════════════════════════════════════════════════


@skip_no_rust
def test_canonical_bytes_deterministic():
    obj = {"b": 2, "a": 1}
    b1 = aidd_intern_core.json_canonical_bytes(obj)
    b2 = aidd_intern_core.json_canonical_bytes({"a": 1, "b": 2})
    assert b1 == b2
    assert isinstance(b1, (bytes, bytearray))


@skip_no_rust
def test_canonical_bytes_compact():
    out = aidd_intern_core.json_canonical_bytes({"a": 1})
    assert out == b'{"a":1}'


# ═══════════════════════════════════════════════════════════════════════════
# 7. read_file_utf8
# ═══════════════════════════════════════════════════════════════════════════


@skip_no_rust
def test_read_file_utf8_basic():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello 世界")
        f.flush()
        path = f.name
    try:
        result = aidd_intern_core.read_file_utf8(path)
        assert result == "hello 世界"
    finally:
        os.unlink(path)


@skip_no_rust
def test_read_file_utf8_missing():
    with pytest.raises(OSError):
        aidd_intern_core.read_file_utf8("/tmp/does_not_exist_xyz.txt")


# ═══════════════════════════════════════════════════════════════════════════
# 8. clip_ansi_string
# ═══════════════════════════════════════════════════════════════════════════


@skip_no_rust
def test_clip_ansi_plain():
    out = aidd_intern_core.clip_ansi_string("Hello, World!", 8)
    # Should truncate: 7 visible chars + ellipsis (U+2026)
    assert "\u2026" in out
    # Visible width should be at most 8 (7 chars + 1 for ellipsis)
    vw = aidd_intern_core.visible_width(out)
    assert vw <= 8


@skip_no_rust
def test_clip_ansi_no_truncation():
    text = "short"
    out = aidd_intern_core.clip_ansi_string(text, 20)
    assert out == text


@skip_no_rust
def test_clip_ansi_preserves_escapes():
    text = "\x1b[31mRed\x1b[0m text here"
    out = aidd_intern_core.clip_ansi_string(text, 8)
    # ANSI codes should be present in output
    assert "\x1b[" in out


@skip_no_rust
def test_clip_ansi_empty():
    assert aidd_intern_core.clip_ansi_string("", 10) == ""


@skip_no_rust
def test_clip_ansi_zero_width():
    assert aidd_intern_core.clip_ansi_string("hello", 0) == "hello"


# ═══════════════════════════════════════════════════════════════════════════
# 9. visible_width
# ═══════════════════════════════════════════════════════════════════════════


@skip_no_rust
def test_visible_width_plain():
    assert aidd_intern_core.visible_width("hello") == 5


@skip_no_rust
def test_visible_width_ansi_ignored():
    text = "\x1b[31mhello\x1b[0m"
    assert aidd_intern_core.visible_width(text) == 5


@skip_no_rust
def test_visible_width_cjk():
    # CJK characters are typically 2 columns wide
    assert aidd_intern_core.visible_width("中文") == 4


@skip_no_rust
def test_visible_width_empty():
    assert aidd_intern_core.visible_width("") == 0


@skip_no_rust
def test_visible_width_mixed():
    text = "\x1b[32mAB中文\x1b[0m"
    # A=1, B=1, 中=2, 文=2 → 6
    assert aidd_intern_core.visible_width(text) == 6


# ═══════════════════════════════════════════════════════════════════════════
# Fallback mechanism tests
# ═══════════════════════════════════════════════════════════════════════════


def test_session_fallback_mechanism():
    """Verify Python fallback works when Rust module is unavailable."""
    from agent.core.session import Session
    from agent.config import Config
    import asyncio

    config = Config(model_name="test-model")
    queue = asyncio.Queue()
    session = Session(
        event_queue=queue,
        config=config,
        session_id="test_session_fallback",
        user_id="test_user",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        with mock.patch("agent.core.session.RUST_AVAILABLE", False):
            saved_path = session.save_trajectory_local(directory=tmpdir)
            assert saved_path is not None
            assert os.path.exists(saved_path)
            with open(saved_path, "r") as f:
                data = json.load(f)
                assert data["session_id"] == "test_session_fallback"
                assert data["upload_status"] == "pending"

        if RUST_AVAILABLE:
            with mock.patch("agent.core.session.RUST_AVAILABLE", True):
                saved_path2 = session.save_trajectory_local(directory=tmpdir)
                assert saved_path2 is not None
                assert os.path.exists(saved_path2)
                with open(saved_path2, "r") as f:
                    data2 = json.load(f)
                    assert data2["session_id"] == "test_session_fallback"


def test_redact_fallback_equivalence():
    """Rust and Python scrub_string should produce identical output."""
    if not RUST_AVAILABLE:
        pytest.skip("Rust not available")
    from agent.core.redact import _PATTERNS, _SECRETY_NAMES

    samples = [
        "hf_" + "A" * 30,
        "sk-ant-" + "B" * 25,
        "sk-" + "C" * 45,
        "ghp_" + "D" * 36,
        "Normal text with no secrets",
        "OPENAI_API_KEY=sk-test123",
    ]
    for s in samples:
        rust_out = aidd_intern_core.scrub_string(s)
        # Python fallback
        py_out = s
        for pat, repl in _PATTERNS:
            py_out = pat.sub(repl, py_out)
        py_out = _SECRETY_NAMES.sub(lambda m: f"{m.group(1)}=[REDACTED]", py_out)
        assert rust_out == py_out, f"Mismatch for input: {s!r}"


@skip_no_rust
def test_format_layered_memories_rust():
    mock_retrieval_res = {
        "rewritten_query": "What are user's design constraints?",
        "categories": [
            {
                "name": "aidd_parameters",
                "description": "Preferred binder target hotspots and hyperparameters",
                "summary": "### AIDD Preferences\n- Target hotspot: GLU45\n- Epochs: 200",
            }
        ],
        "items": [
            {
                "memory_type": "preference",
                "content": "Prefers standard protein design pipelines",
            },
            {"memory_type": "constraint", "content": "Must fit within 12GB GPU VRAM"},
        ],
    }

    res = aidd_intern_core.format_layered_memories_rust(mock_retrieval_res, "Alice")
    assert len(res["L1_atomic"]) == 2
    assert res["L1_atomic"][0]["type"] == "preference"
    assert res["L1_atomic"][0]["content"] == "Prefers standard protein design pipelines"

    assert "aidd_parameters" in res["L2_scenarios"]
    assert "GLU45" in res["L2_scenarios"]["aidd_parameters"]["summary"]

    assert "# Alice Profile & Persona" in res["L3_profile"]
    assert "Must fit within 12GB GPU VRAM" in res["L3_profile"]

    prompt = res["formatted_prompt"]
    assert "🧠 LAYERED LONG-TERM MEMORY ENGINE" in prompt
    assert "[L3: USER PROFILE & PERSONA]" in prompt
    assert "[L2: ACTIVE SCENARIO BLOCKS]" in prompt
    assert "[L1: ATOMIC FACTS & PREFERENCES]" in prompt
    assert "1. [PREFERENCE] Prefers standard protein design pipelines" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# Performance benchmarks
# ═══════════════════════════════════════════════════════════════════════════


def test_benchmark_json_dumps():
    """Compare Rust json_dumps_sorted vs Python json.dumps(sort_keys=True)."""
    if not RUST_AVAILABLE:
        pytest.skip("Rust not available")

    trajectory = {
        "session_id": "bench",
        "events": [
            {"type": "llm", "prompt": "x" * 5000, "response": "y" * 5000}
            for _ in range(50)
        ],
    }

    iters = 10

    t0 = time.perf_counter()
    for _ in range(iters):
        json.dumps(trajectory, sort_keys=True, ensure_ascii=False)
    py_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    for _ in range(iters):
        aidd_intern_core.json_dumps_sorted(trajectory)
    rust_time = time.perf_counter() - t1

    print(
        f"\n[json_dumps] Python: {py_time:.4f}s | Rust: {rust_time:.4f}s | "
        f"Speedup: {py_time / max(rust_time, 1e-9):.2f}x"
    )


def test_benchmark_scrub():
    """Compare Rust scrub_string vs Python regex chain."""
    if not RUST_AVAILABLE:
        pytest.skip("Rust not available")
    from agent.core.redact import _PATTERNS, _SECRETY_NAMES

    sample = (
        "Authorization: Bearer " + "A" * 60 + "\n"
        "HF_TOKEN=hf_" + "B" * 40 + "\n"
        "sk-" + "C" * 50 + "\n"
        "Normal log line\n" * 100
    )

    iters = 50

    t0 = time.perf_counter()
    for _ in range(iters):
        out = sample
        for pat, repl in _PATTERNS:
            out = pat.sub(repl, out)
        _SECRETY_NAMES.sub(lambda m: f"{m.group(1)}=[REDACTED]", out)
    py_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    for _ in range(iters):
        aidd_intern_core.scrub_string(sample)
    rust_time = time.perf_counter() - t1

    print(
        f"\n[scrub] Python: {py_time:.4f}s | Rust: {rust_time:.4f}s | "
        f"Speedup: {py_time / max(rust_time, 1e-9):.2f}x"
    )


def test_benchmark_file_io():
    """Compare Rust save_json_atomic vs Python atomic write."""
    if not RUST_AVAILABLE:
        pytest.skip("Rust not available")

    payload = json.dumps(
        {"events": [{"data": "x" * 10000} for _ in range(100)]}
    ).encode()

    with tempfile.TemporaryDirectory() as tmpdir:
        iters = 5

        t0 = time.perf_counter()
        for i in range(iters):
            p = os.path.join(tmpdir, f"py_{i}.json")
            tmp = p + ".tmp"
            with open(tmp, "wb") as f:
                f.write(payload)
            os.replace(tmp, p)
        py_time = time.perf_counter() - t0

        t1 = time.perf_counter()
        for i in range(iters):
            p = os.path.join(tmpdir, f"rust_{i}.json")
            aidd_intern_core.save_json_atomic(p, payload)
        rust_time = time.perf_counter() - t1

        print(
            f"\n[file_io] Python: {py_time:.4f}s | Rust: {rust_time:.4f}s | "
            f"Speedup: {py_time / max(rust_time, 1e-9):.2f}x"
        )


def test_search_wiki_entries_rust():
    """Verify search_wiki_entries_rust correctness and filter matches."""
    if not RUST_AVAILABLE:
        pytest.skip("Rust not available")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a few entry JSON files
        entry_a = {
            "id": "wiki-a",
            "title": "PD-L1 high temperature optimization",
            "category": "strategy",
            "target": "PD-L1",
            "tool_chain": ["run_bindcraft", "run_esmfold"],
            "params": {"temperature": 0.5, "num_samples": 20},
            "outcome": {"ipTM": "0.85"},
            "lessons": ["Keep temperature high.", "Monitor clashes."],
            "tags": ["strategy", "pd-l1", "run_bindcraft"],
            "created_at": "2026-05-20T12:00:00Z",
            "helpful_count": 5,
            "harmful_count": 1,
        }
        entry_b = {
            "id": "wiki-b",
            "title": "HER2 binding clash resolution",
            "category": "failure_mode",
            "target": "HER2",
            "tool_chain": ["run_pxdesign"],
            "params": {"iterations": 5},
            "outcome": {"clashes": "12"},
            "lessons": ["Clashes detected under default run.", "Reduce temperature."],
            "tags": ["failure_mode", "her2", "run_pxdesign"],
            "created_at": "2026-05-25T12:00:00Z",
            "helpful_count": 2,
            "harmful_count": 0,
        }

        with open(os.path.join(tmpdir, "wiki-a.json"), "w") as f:
            json.dump(entry_a, f)
        with open(os.path.join(tmpdir, "wiki-b.json"), "w") as f:
            json.dump(entry_b, f)

        current_time_iso = "2026-05-29T12:00:00Z"

        # 1. Search with common term
        results = aidd_intern_core.search_wiki_entries_rust(
            tmpdir, "temperature", current_time_iso, top_k=5
        )
        assert (
            len(results) == 2
        )  # Both mention temperature (entry_a in title/lessons, entry_b in lessons)

        parsed_results = [json.loads(r) for r in results]
        assert (
            parsed_results[0]["id"] == "wiki-a"
        )  # wiki-a has higher match (title + effectiveness + helpful)

        # 2. Filter by category
        results_cat = aidd_intern_core.search_wiki_entries_rust(
            tmpdir, "temperature", current_time_iso, category="failure_mode", top_k=5
        )
        assert len(results_cat) == 1
        assert json.loads(results_cat[0])["id"] == "wiki-b"

        # 3. Filter by target
        results_tgt = aidd_intern_core.search_wiki_entries_rust(
            tmpdir, "PD-L1", current_time_iso, target="PD-L1", top_k=5
        )
        assert len(results_tgt) == 1
        assert json.loads(results_tgt[0])["id"] == "wiki-a"


def test_skill_extraction_rust():
    """Verify is_binder_design_session_rust and search_skills_rust."""
    if not RUST_AVAILABLE:
        pytest.skip("Rust not available")

    # 1. Test binder design session heuristic
    msg_a = ["Hello", "Let's plan binder design campaign on target_pdb"]
    assert (
        aidd_intern_core.is_binder_design_session_rust(msg_a) is True
    )  # keywords: binder, target_pdb

    msg_b = ["How are you?", "I like programming in Python"]
    assert aidd_intern_core.is_binder_design_session_rust(msg_b) is False

    # 2. Test parallel skill search
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_a_content = """# PD-L1 bindcraft optimization
## Trigger
pd-l1 target bindcraft run
## Metadata
- **Target:** PD-L1
- **Tool Chain:** run_bindcraft
"""
        skill_b_content = """# HER2 clash recovery
## Trigger
her2 target pxdesign run
## Metadata
- **Target:** HER2
- **Tool Chain:** run_pxdesign
"""
        with open(os.path.join(tmpdir, "skill-a.md"), "w") as f:
            f.write(skill_a_content)
        with open(os.path.join(tmpdir, "skill-b.md"), "w") as f:
            f.write(skill_b_content)

        # Search term in metadata
        res = aidd_intern_core.search_skills_rust(tmpdir, "bindcraft", top_k=5)
        assert len(res) == 1
        assert "skill-a.md" in res[0][0]
        assert res[0][1] >= 1.0

        # Search term in target
        res_her2 = aidd_intern_core.search_skills_rust(tmpdir, "HER2", top_k=5)
        assert len(res_her2) == 1
        assert "skill-b.md" in res_her2[0][0]
