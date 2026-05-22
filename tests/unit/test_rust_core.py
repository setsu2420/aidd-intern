import os
import tempfile
import json
import time
import pytest
from unittest import mock
from pathlib import Path

# 测试 aidd_intern_core 模块是否可用
try:
    import aidd_intern_core

    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False


@pytest.mark.skipif(
    not RUST_AVAILABLE, reason="aidd_intern_core Rust module is not compiled"
)
def test_rust_core_atomic_save():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_file.json")
        data = {"hello": "world", "aidd": "intern"}
        content_bytes = json.dumps(data, indent=2).encode("utf-8")

        # 测试正常写入
        aidd_intern_core.save_json_atomic(test_file, content_bytes)

        assert os.path.exists(test_file)
        with open(test_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)

        assert saved_data == data


@pytest.mark.skipif(
    not RUST_AVAILABLE, reason="aidd_intern_core Rust module is not compiled"
)
def test_rust_core_invalid_path():
    # 测试在无法创建的无权限路径下写入是否能正确抛出异常
    content_bytes = b"test"
    with pytest.raises(Exception):
        aidd_intern_core.save_json_atomic(
            "/nonexistent_directory_for_sure/test.json", content_bytes
        )


def test_session_fallback_mechanism():
    # Mock aidd_intern_core 不存在或失败的情况，验证 Fallback 优雅降级机制
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
        # 1. 强制将 RUST_AVAILABLE 设为 False，测试原生的 Python Fallback 路径
        with mock.patch("agent.core.session.RUST_AVAILABLE", False):
            saved_path = session.save_trajectory_local(directory=tmpdir)
            assert saved_path is not None
            assert os.path.exists(saved_path)
            with open(saved_path, "r") as f:
                data = json.load(f)
                assert data["session_id"] == "test_session_fallback"
                assert data["upload_status"] == "pending"

        # 2. 如果 Rust 模块确实存在，则在 RUST_AVAILABLE=True 的情况下测试 Rust 写入路径
        if RUST_AVAILABLE:
            with mock.patch("agent.core.session.RUST_AVAILABLE", True):
                saved_path2 = session.save_trajectory_local(directory=tmpdir)
                assert saved_path2 is not None
                assert os.path.exists(saved_path2)
                with open(saved_path2, "r") as f:
                    data2 = json.load(f)
                    assert data2["session_id"] == "test_session_fallback"


def test_performance_benchmark():
    # 比较 Python 和 Rust 在写入大量数据时的速度与响应差异
    if not RUST_AVAILABLE:
        pytest.skip("aidd_intern_core Rust module is not compiled, skipping benchmark")

    import aidd_intern_core

    # 模拟一个中等偏大、高度复杂的智能体会话 Trace 轨迹数据（比如包含多轮LLM长输入输出）
    mock_trajectory = {
        "session_id": "benchmark_session",
        "events": [
            {
                "event_type": "llm_call",
                "prompt": "x" * 10000,
                "response": "y" * 10000,
            }
            for _ in range(100)
        ],
    }
    content_bytes = json.dumps(mock_trajectory, indent=2).encode("utf-8")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 测试 Python 原生落盘方式（多次写入以减少环境噪音）
        py_file = os.path.join(tmpdir, "py.json")
        t0 = time.perf_counter()
        for _ in range(5):
            tmp_path = Path(py_file).with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(mock_trajectory, f, indent=2)
            tmp_path.replace(py_file)
        py_time = time.perf_counter() - t0

        # 2. 测试 Rust 高性能原子落盘方式
        rust_file = os.path.join(tmpdir, "rust.json")
        t1 = time.perf_counter()
        for _ in range(5):
            aidd_intern_core.save_json_atomic(rust_file, content_bytes)
        rust_time = time.perf_counter() - t1

        print("\n=================== BENCHMARK RESULTS ===================")
        print(f"Python Native write total time: {py_time:.6f}s")
        print(f"Rust GIL-Free write total time: {rust_time:.6f}s")
        if rust_time > 0:
            print(f"Speedup Ratio:                  {py_time / rust_time:.2f}x")
        print("=========================================================")
