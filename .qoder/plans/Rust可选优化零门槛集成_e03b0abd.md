# Rust 可选优化零门槛集成

核心目标：`uv sync` 一步到位。有 Rust 自动编译加速，无 Rust 静默 fallback。直接在 main 分支操作。

## Task 1: 修改 pyproject.toml 构建后端

将 `[build-system]` 从 maturin 切换到 setuptools + setuptools-rust：
- `requires = ["setuptools>=68.0", "setuptools-rust>=1.8"]`
- `build-backend = "setuptools.build_meta"`
- 移除 `[tool.maturin]` 块
- 添加 `[tool.setuptools.packages.find]` 包含 agent/aidd_intern_core/backend

## Task 2: 创建 setup.py

使用 setuptools-rust 的 `RustExtension(optional=True)`：
- `optional=True` 使 Rust 不可用时静默跳过编译
- PyO3 binding 模式
- 指向根目录 Cargo.toml

## Task 3: 添加 scripts/setup-rust.sh

一键安装 Rust + 编译 release 版本：
- 检测 rustc 是否存在，不存在则自动安装 rustup
- 调用 `maturin develop --release`（或 `pip install -e .`）
- 输出明确的成功/失败提示

## Task 4: 更新文档

- **AGENTS.md**: 添加 Rust 可选加速章节，说明 uv sync 自动检测、fallback 行为、scripts/setup-rust.sh 用法
- **README.md / README.zh-CN.md / README.ja.md**: 添加"Rust 加速（可选）"段落

## Task 5: 验证

1. 有 Rust: `uv sync` -> 自动编译 -> pytest 通过
2. ruff check + ruff format
3. 提交到 main 并 push

## Task 6: 清理

- 确认旧的 `rust_core/` 目录是否仍需要（可能已被根级 Cargo.toml 替代）
- 清理 feature 分支（如 feat/rust-core-optimization 远程分支）
