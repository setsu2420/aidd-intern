<p align="center">
    <a href="https://github.com/setsu2420/aidd-intern/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
    <a href="https://smolagents-aidd-intern.hf.space/"><img alt="Website" src="https://img.shields.io/website/https/smolagents-aidd-intern.hf.space.svg?down_color=red&down_message=offline&up_message=online"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <strong>简体中文</strong> · <a href="README.ja.md">日本語</a>
</p>

# AIDD-Intern

AIDD-Intern 是一个面向 AI 药物研发（AI Drug Discovery, AIDD）的 AI Agent 异步运行时系统。它解耦了 LLM 调用、上下文管理、工具路由、MCP 集成、会话追踪、Web 后端及 AIDD 专属领域工具。

## 目录

- [核心功能](#核心功能)
- [快速开始](#快速开始)
- [本地更新](#本地更新)
- [本地诊断](#本地诊断)
- [AIDD 准备阶段](#aidd-准备阶段)
- [项目结构](#项目结构)

## 核心功能

- **文献与数据调研**：通过内置的检索工具，为药物研发决策收集最新文献、代码仓库及模型信息。
- **AIDD 准备阶段**：自动创建准备项目、下载 PDB 结构、剪裁目标链，并对接触残基热点进行排序。
- **MCP 科学工具集成**：支持 Hugging Face MCP 及本地 ProteinMCP（BindCraft, BoltzGen, PXDesign）的轻量级冷启动与调用。
- **自适应上下文**：根据模型与 Token 限制，在运行时自动执行上下文压缩，防止长任务中断。
- **双轨优雅降级**：内置基于 PyO3 + Maturin 的高性能 Trace 写入加速模块。若系统未安装 Rust 编译环境，将自动且无缝地降级至原生 Python 写入引擎。

## 快速开始

### 依赖环境

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (快速 Python 包管理器)
- Git (用于源码管理)

### 安装与配置

请在终端中执行以下命令进行安装：

```bash
git clone https://github.com/setsu2420/aidd-intern.git
cd aidd-intern
uv sync --extra dev
uv tool install -e .
```

> **注意**：必须在 `cd aidd-intern` 进入目录后再运行 `uv sync` and `uv tool install -e .`，因为依赖解析和工具安装需要读取该目录下的 `pyproject.toml` 文件。

如果由于网络原因在 `git clone` 时遇到 HTTPS 传输层错误，可强制使用 HTTP/1.1 进行浅克隆尝试：
```bash
git -c http.version=HTTP/1.1 clone --depth 1 https://github.com/setsu2420/aidd-intern.git
```
或者，使用集成了归档包下载与自动容错的引导脚本进行一键安装：
```bash
curl -fsSL https://raw.githubusercontent.com/setsu2420/aidd-intern/main/scripts/bootstrap-source.sh | bash
```

安装完成后，请配置环境变量。从模板创建 `.env` 文件：
```bash
cp .env.example .env
```
编辑 `.env` 文件，配置您所用模型对应的 API Key（如 `SILICONFLOW_API_KEY` 或 `OPENROUTER_API_KEY`）及 `AIDD_INTERN_DEFAULT_MODEL_ID`。

## 本地诊断

在安装、修改配置或更新后，建议运行诊断命令以验证环境是否正常：
```bash
aidd-intern --doctor
```
该命令为只读操作，将逐步检查 Python、Git、uv、配置文件、LLM API 凭证及 ProteinMCP 设置。

## 本地更新

若需更新本地源码至最新版本，可在仓库根目录下运行：
```bash
scripts/update-local.sh
```
该脚本将无损地执行 `git pull --ff-only origin <current-branch>`、`uv sync --extra dev` 及 `uv tool install -e .` 以刷新依赖与命令行工具。

## Rust 加速（可选）

AIDD-Intern 内置了可选的 Rust 原生扩展模块（`aidd_intern_core`），可为 JSON 序列化、敏感信息清洗及 ANSI 字符串处理提供最高 **3.2 倍**的加速，并支持 GIL-free 并发。

**Rust 扩展完全可选** — 若您的系统未安装 Rust 工具链，项目将自动使用纯 Python 实现，零配置即可正常运行。

### 自动检测（推荐）

如果您已安装 Rust，只需运行：
```bash
uv sync --extra dev
```
构建系统（`setuptools-rust`）会自动检测并编译原生扩展。

### 一键安装（安装 Rust + 编译）

如果您尚未安装 Rust，运行以下脚本：
```bash
./scripts/setup-rust.sh
```
该脚本会通过 `rustup` 自动安装 Rust 工具链（若不存在），并编译 release 优化版本的原生扩展。

### 手动配置

1. 安装 Rust：
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
   source $HOME/.cargo/env
   ```
2. 重新构建项目：
   ```bash
   uv sync --extra dev
   ```

### 验证

```bash
python -c "from aidd_intern_core import json_dumps_sorted; print(json_dumps_sorted({'hello': 'world'}))"
```
若无报错，则 Rust 加速已启用。

## AIDD 准备阶段

在运行 binder 科学计算生成任务之前，需完成以下四个本地准备任务：
1. **文献资料调研**：收集靶点、已知 binder、结合表位及实验约束的元数据。
2. **PDB 文件获取下载**：从 RCSB PDB 数据库下载指定的实验三维结构。
3. **结构剪裁**：保留下游设计工具所需的特定目标链或结构域残基范围。
4. **热点残基确定**：基于目标链与伴侣链的非氢原子接触排序，初步筛选热点残基候选。

您可以通过命令行一键运行完整的准备流程：
```bash
aidd-intern --prepare-aidd \
  --target-name "PD-L1" \
  --pdb-id 4ZQK \
  --target-chains A \
  --partner-chains B \
  --residue-ranges A:19-134 \
  --prep-project-dir runs/pd-l1-prep
```
该流程将自动在输出目录中写入以下结构化产物：
- `aidd_preparation_manifest.json` (项目元数据配置)
- `literature/literature_sources.md` (调研文献来源)
- `structures/raw/<PDB_ID>.pdb` (原始结构)
- `structures/cropped/<PDB_ID>_<chains>_crop.pdb` (剪裁后的结构)
- `analysis/hotspots.json` (接触残基分析结果)
- `aidd_preparation_summary.md` (准备工作总结报告)

> **安全提示**：`aidd_prepare` 提供的热点残基筛选仅作为准备阶段的输入候选，并不等同于实验结合能证明。

## 项目结构

- `agent/`：Agent 运行时、上下文管理、命令行入口及内置工具。
- `backend/`：FastAPI Web 后端服务，负责会话管理与 API 路由。
- `configs/`：共享模型目录及 MCP 配置。
- `aidd_intern_core/`：Rust 原生扩展的 Python 包装器（Rust 可用时自动编译）。
- `src/`：Rust 原生扩展源代码（`lib.rs`）。
- `scripts/`：本地开发启动器、科学工具 MCP 安装与一键配置工具。
- `tests/`：pytest 单元测试与集成测试套件。