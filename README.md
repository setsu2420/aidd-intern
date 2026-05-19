<p align="center">
    <a href="https://github.com/huggingface/aidd-intern/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
    <a href="https://smolagents-aidd-intern.hf.space/"><img alt="Website" src="https://img.shields.io/website/https/smolagents-aidd-intern.hf.space.svg?down_color=red&down_message=offline&up_message=online"></a>
</p>

# AIDD-Intern

AIDD-Intern 是一个面向 AI drug discovery 的异步智能体运行时。它把 LLM
模型调用、上下文管理、工具路由、MCP、会话追踪、Web UI 和 AIDD
领域工具分开实现，让同一个项目既能做无 GPU 的资料调研，也能在具备外部
计算资源时调度 binder/protein design 工作流。

本项目不会在本地进程中加载 LLM 权重，也不会把 BindCraft、BoltzGen、
PXDesign、Chai-1、Protenix 等重型科学工具直接导入 FastAPI 或 CLI
进程。没有本地 GPU 时，推荐使用远程 LLM API 和 `--domain-pack none`
做调研任务；需要生成或验证蛋白 binder 时，再通过 MCP、子进程、容器、集群
或 Hugging Face Jobs 接入对应工具。

## 目录

- [核心功能](#核心功能)
- [快速开始](#快速开始)
- [配置 API 和搜索](#配置-api-和搜索)
- [使用说明](#使用说明)
- [工具和 MCP 配置](#工具和-mcp-配置)
- [BindCraft、BoltzGen、PXDesign](#bindcraftboltzgenpxdesign)
- [上下文和模型策略](#上下文和模型策略)
- [项目结构](#项目结构)
- [开发和测试](#开发和测试)
- [会话追踪和分享](#会话追踪和分享)

## 核心功能

- **带来源链接的调研**：内置 `research` 子智能体、`web_search`、
  `literature_lookup`、`hf_papers`、GitHub/HF 文档工具和 `aidd_bio`。
  调研输出要求给出论文、官方文档、代码仓库、数据集/模型卡或网页链接。
- **真正的 Google Search**：配置 `GOOGLE_SEARCH_API_KEY` 和
  `GOOGLE_SEARCH_ENGINE_ID` 后，`web_search` 使用 Google Custom Search
  JSON API，并支持 `recent_days` 和 `sort_by_date` 优先查找近期资料。
- **AIDD binder 工作流**：默认 `aidd_binder` 域包提供
  `binder_design`，用于规划 binder campaign、创建项目 manifest、检查
  generator 输出、排序候选 binder、标记验证缺口并导出可复用 skill card。
- **Protein design 扩展**：可选 `protein_design` 域包提供 PXDesign、
  BoltzGen、BindCraft 生成工具，以及 Chai-1、Protenix、Foldseek 验证边界。
- **MCP 集成**：默认配置 Hugging Face MCP 和本地 ProteinMCP stdio
  launcher。冷启动会跳过当前不可用的 MCP，避免无 token 或无 GPU 时阻塞。
- **上下文窗口自适应**：运行时会根据接入模型和
  `AIDD_INTERN_MODEL_MAX_TOKENS` 调整压缩策略。未知本地模型默认采用保守的
  65,536 token 策略，避免长任务因上下文溢出失败。
- **本地 CLI 和 Web UI**：Python CLI 用于真实交互式/无头智能体运行；
  FastAPI + React Web UI 用于浏览器会话；Node.js CLI 用于 smoke、
  integration 和 eval 测试。
- **会话追踪**：会话可保存为 Claude Code JSONL 兼容格式，并上传到用户自己的
  Hugging Face 私有 dataset，便于复盘工具调用和模型回答。

## 快速开始

### 依赖

- Python 3.11+
- `uv`
- Git
- Node.js 22+，仅在开发前端或 npm harness 时需要
- Conda/Mamba 和 GPU，仅在安装 PXDesign、BindCraft 等本地科学工具时需要

### 安装 Python 运行时

```bash
git clone git@github.com:huggingface/aidd-intern.git
cd aidd-intern
uv sync --extra dev
uv tool install -e .
```

安装后可以从任意目录运行：

```bash
aidd-intern
```

### 无本地 GPU 的调研模式

如果只希望完成调研、资料查找、代码阅读和方案整理，不运行 binder/protein
生成工具，使用 `none` 域包：

```bash
aidd-intern --domain-pack none --model openrouter/openai/gpt-5.2 \
  "调研 2026 年最新的 protein binder design 工具。请优先使用 Google Search，给出来源链接和发布日期。"
```

这种模式会保留通用工具、Web 搜索、论文/文档/GitHub 检索和本地文件工具，
但不会启用 binder/protein 专用工具提示。

### 本地 Web App

从仓库根目录启动后端和前端：

```bash
./scripts/dev.sh
```

默认地址：

- 前端：`http://localhost:5173/`
- 后端健康检查：`curl -g http://[::1]:7860/api`
- 前端代理检查：`curl http://localhost:5173/api`

也可以分开启动：

```bash
cd backend
uv run python -m uvicorn main:app --host ::1 --port 7860
```

```bash
cd frontend
npm ci
npm run dev
```

## 配置 API 和搜索

在仓库根目录创建 `.env`，或在 shell 中导出变量。不要把 `.env`、token、
模型权重、数据库、checkpoint 或生成的结构批次提交到 GitHub。

```bash
# LLM provider，根据你选择的模型设置其一或多个
OPENAI_API_KEY=<your-openai-api-key>
ANTHROPIC_API_KEY=<your-anthropic-api-key>
OPENROUTER_API_KEY=<your-openrouter-api-key>
SILICONFLOW_API_KEY=<your-siliconflow-api-key>

# 默认模型。也可以每次用 --model 覆盖
AIDD_INTERN_DEFAULT_MODEL_ID=openrouter/openai/gpt-5.2

# 真正的 Google Search。两个变量必须同时设置
GOOGLE_SEARCH_API_KEY=<google-custom-search-json-api-key>
GOOGLE_SEARCH_ENGINE_ID=<programmable-search-engine-id>

# 可选别名，代码也会识别
GOOGLE_API_KEY=<google-custom-search-json-api-key>
GOOGLE_CSE_ID=<programmable-search-engine-id>

# Hugging Face 与 GitHub 工具
HF_TOKEN=<your-hugging-face-token>
GITHUB_TOKEN=<github-personal-access-token>

# 本地或局域网 OpenAI-compatible 推理服务，可选
LOCAL_LLM_BASE_URL=http://localhost:8000
LOCAL_LLM_API_KEY=<optional-local-api-key>

# ProteinMCP 本地安装目录，可选
AIDD_INTERN_PROTEINMCP_HOME=~/.cache/aidd-intern/proteinmcp
```

相关官方入口：

- Google Custom Search JSON API:
  https://developers.google.com/custom-search/v1/overview
- Google Programmable Search Engine:
  https://programmablesearchengine.google.com/
- OpenAI API keys: https://platform.openai.com/api-keys
- Anthropic Console: https://console.anthropic.com/
- OpenRouter API keys: https://openrouter.ai/settings/keys
- Hugging Face access tokens:
  https://huggingface.co/docs/hub/security-tokens
- GitHub fine-grained personal access tokens:
  https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens

### Google Search 行为

`web_search` 的优先级如下：

1. 同时设置 `GOOGLE_SEARCH_API_KEY` 和 `GOOGLE_SEARCH_ENGINE_ID` 时，使用
   Google Custom Search JSON API。
2. 调用参数包含 `recent_days` 时，Google 请求会发送 `dateRestrict=dN`。
3. 调用参数包含 `sort_by_date=true` 时，Google 请求会发送 `sort=date`。
4. 没有 Google 凭据时，开发环境会使用内置 HTML 搜索 fallback，并在结果中标注
   provider。
5. 已配置 Google 但 Google 返回错误时，默认直接报错。只有设置
   `AIDD_INTERN_ALLOW_WEB_SEARCH_FALLBACK=1` 才会退回 fallback。

可以用真实 Google 凭据跑 live test：

```bash
PYTHONDONTWRITEBYTECODE=1 AIDD_INTERN_LIVE_WEB_SEARCH_TESTS=1 \
  uv run pytest -p no:cacheprovider tests/integration/test_web_search_live.py -s
```

该测试会调用真实 Google Custom Search。未配置凭据时会跳过，不使用 mock data。

## 使用说明

### Python 智能体 CLI

交互模式：

```bash
aidd-intern
```

无头模式，单次任务：

```bash
aidd-intern "调研最新的 AlphaFold-style complex validation 方法，并给出来源链接"
```

常用参数：

```bash
aidd-intern --model openai/gpt-5.5 "your prompt"
aidd-intern --model anthropic/claude-opus-4-7 "your prompt"
aidd-intern --model openrouter/openai/gpt-5.2 "your prompt"
aidd-intern --model siliconflow/deepseek-ai/DeepSeek-V4-Flash "your prompt"
aidd-intern --domain-pack none "research-only task"
aidd-intern --domain-pack aidd_binder "plan a binder campaign"
aidd-intern --domain-pack protein_design "run protein design tools"
aidd-intern --sandbox-tools "test this script in an HF Space sandbox"
aidd-intern --max-iterations 100 "long task"
aidd-intern --no-stream "disable streaming"
```

交互模式内可以用 `/model` 查看和切换模型：

```text
/model
/model openrouter/openai/gpt-5.2
/model ollama/llama3.1:8b
```

### 本地 OpenAI-compatible 模型

AIDD-Intern 通过 LiteLLM 调用 OpenAI-compatible HTTP 服务。它不负责启动
Ollama、vLLM、LM Studio 或 llama.cpp，也不会在 CLI 进程中加载模型权重。

```bash
aidd-intern --model ollama/llama3.1:8b "your prompt"
aidd-intern --model vllm/Qwen/Qwen3-Coder-30B-A3B-Instruct "your prompt"
aidd-intern --model lm_studio/google/gemma-3-4b "your prompt"
aidd-intern --model llamacpp/qwen3.6-35b-a3b-gguf "your prompt"
```

支持的本地前缀包括 `ollama/`、`vllm/`、`lm_studio/`、`llamacpp/`。可用
`LOCAL_LLM_BASE_URL` 和 `LOCAL_LLM_API_KEY` 设置共享端点，也可以用
`OLLAMA_BASE_URL`、`VLLM_API_KEY` 等 provider-specific 变量覆盖。

### Node.js CLI package

`src/` 下的 Node CLI 是后端测试和评测 harness，不是 Python 交互式智能体。
它适合 CI 或发布 npm package 后给用户跑 smoke、integration、eval。

```bash
npm ci
npm run build
npm run lint
npm test
npm pack --dry-run
```

连接本地或线上后端：

```bash
aidd-intern --url http://[::1]:7860 smoke
aidd-intern --json integration
aidd-intern eval --fixtures fixtures/prompts.json --limit 3
aidd-intern eval --judge
```

注意：Python CLI 和 Node CLI 都叫 `aidd-intern`。开发时优先明确当前 PATH
指向的是 `uv tool install -e .` 安装的 Python 运行时，还是 `npm link`/全局
npm 安装的 Node harness。

## 工具和 MCP 配置

默认配置文件：

- CLI: `configs/cli_agent_config.json`
- Web: `configs/frontend_agent_config.json`

用户级 CLI 配置：

```bash
~/.config/aidd-intern/cli_agent_config.json
```

也可以用环境变量指定：

```bash
AIDD_INTERN_CLI_CONFIG=/path/to/cli_agent_config.json
```

配置文件支持 `${VAR}` 和 `${VAR:-default}` 环境变量替换。新增或修改 MCP
默认值时，请保持 CLI 和 frontend 配置一致，除非确实需要差异。

默认 MCP：

- `hf-mcp-server`: HTTP endpoint `https://hf.co/mcp`。未设置 `HF_TOKEN`
  时冷启动会跳过，避免 Hugging Face OAuth 登录错误拖慢启动。
- `proteinmcp-bindcraft`: 本地 stdio launcher。
- `proteinmcp-boltzgen`: 本地 stdio launcher。
- `proteinmcp-pxdesign`: 本地 stdio launcher。

ProteinMCP 的冷启动规则：

- `--domain-pack protein_design` 时自动尝试连接 ProteinMCP。
- 其他域包下，只有设置 `AIDD_INTERN_ENABLE_PROTEINMCP=1` 才会连接。
- launcher 会自动 clone 缺失 repo，但默认不会运行重型 `quick_setup.sh`。
  如果确实想让 launcher 自动 setup，设置
  `AIDD_INTERN_PROTEINMCP_AUTO_SETUP=1`。

## BindCraft、BoltzGen、PXDesign

这些工具用于真实 binder/protein design，通常需要 GPU、Conda/Mamba、
模型权重和较长运行时间。无 GPU 的本地电脑建议只做调研、规划、候选结果解读
和报告整理，不直接运行生成任务。

### 一次性安装

安装全部本地 ProteinMCP 工具：

```bash
scripts/setup-proteinmcp-local.sh all
```

只安装某一个：

```bash
scripts/setup-proteinmcp-local.sh bindcraft_mcp
scripts/setup-proteinmcp-local.sh boltzgen_mcp
scripts/setup-proteinmcp-local.sh pxdesign_mcp
```

默认安装目录：

```bash
~/.cache/aidd-intern/proteinmcp
```

可通过环境变量覆盖：

```bash
AIDD_INTERN_PROTEINMCP_HOME=/data/aidd-intern/proteinmcp
```

### 本地启动单个 MCP server

```bash
scripts/run-proteinmcp-local.sh bindcraft_mcp
scripts/run-proteinmcp-local.sh boltzgen_mcp
scripts/run-proteinmcp-local.sh pxdesign_mcp
```

### BindCraft

默认 repo：

```bash
https://github.com/MacromNex/bindcraft_mcp.git
```

安装 BindCraft MCP：

```bash
scripts/setup-proteinmcp-local.sh bindcraft_mcp
```

更轻量的安装方式：

```bash
AIDD_INTERN_BINDCRAFT_SETUP_ARGS=--skip-weights \
  scripts/setup-proteinmcp-local.sh bindcraft_mcp
```

`--skip-weights` 可以让 MCP 环境先搭起来，但没有 AlphaFold2 权重时不能运行完整
design。已有内部 BindCraft wrapper 时，可以让 protein design 域包直接调用：

```bash
PROTEIN_DESIGN_BINDCRAFT_CMD=/opt/bindcraft/run_bindcraft.sh
```

### BoltzGen

默认 repo：

```bash
https://github.com/MacromNex/boltzgen_mcp.git
```

安装：

```bash
scripts/setup-proteinmcp-local.sh boltzgen_mcp
```

BoltzGen setup 默认带 `--skip-models`，避免安装时卡在模型下载。需要安装阶段下载
模型时：

```bash
AIDD_INTERN_BOLTZGEN_SETUP_ARGS=--download-models \
  scripts/setup-proteinmcp-local.sh boltzgen_mcp
```

已有 wrapper 时：

```bash
PROTEIN_DESIGN_BOLTZGEN_CMD=/opt/boltzgen/bin/boltzgen
```

### PXDesign

默认 repo：

```bash
https://github.com/bytedance/PXDesign.git
```

安装：

```bash
scripts/setup-proteinmcp-local.sh pxdesign_mcp
```

PXDesign setup 使用官方 Conda installer，不使用 Docker。没有 `nvidia-smi`
或 CUDA 自动检测失败时，显式指定 CUDA：

```bash
AIDD_INTERN_PXDESIGN_CUDA_VERSION=12.1 \
  scripts/setup-proteinmcp-local.sh pxdesign_mcp
```

已有 PXDesign CLI 时：

```bash
PXDESIGN_BIN=/opt/pxdesign/bin/pxdesign
PROTEIN_DESIGN_PXDESIGN_CMD=/opt/pxdesign/bin/pxdesign
```

### GPU 和重型资产

不要提交以下内容：

- AlphaFold2/BindCraft/PXDesign/BoltzGen 权重
- checkpoint、数据库、索引和大型结构批次
- 生成结果目录、trace dump、私有数据集

推荐将大型资产放在本地 cache、共享文件系统、对象存储、Hugging Face Hub 私有
repo、容器 volume 或集群路径，再用环境变量指向它们。

Protein design 工具会尽量检查 GPU 空闲显存。没有 `nvidia-smi` 但调度器已分配
显存时，可以提供 hint：

```bash
PROTEIN_DESIGN_GPU_FREE_MB=24000
```

## 域包

支持的 `--domain-pack`：

- `aidd_binder`：默认域包。提供 `binder_design`，用于 binder campaign
  规划、manifest、输出检查、候选排序、验证缺口标记和 skill 导出。详见
  `docs/aidd-binder-workflow-guide.md`。
- `protein_design`：启用 PXDesign、BoltzGen、BindCraft 生成工具，Chai-1、
  Protenix、Foldseek 验证边界，以及 ACE-style campaign memory。需要外部工具
  和通常意义上的 GPU 环境。
- `none`：通用运行时，不加载领域专用工作流工具。适合无 GPU 调研、代码阅读、
  文档整理和普通工程任务。

配置文件覆盖示例：

```json
{
  "domain_pack": "protein_design"
}
```

## 上下文和模型策略

AIDD-Intern 的上下文预算不固定，应随接入 LLM 调整：

- 运行时会读取模型/provider 信息。
- 未知本地模型默认使用保守 65,536 token 策略。
- 上下文接近阈值时会触发压缩，减少长任务因 provider context window
  错误中断。
- 可用 `AIDD_INTERN_MODEL_MAX_TOKENS` 显式覆盖。

示例：

```bash
AIDD_INTERN_MODEL_MAX_TOKENS=32768 \
  aidd-intern --model vllm/my-small-model "your prompt"

AIDD_INTERN_MODEL_MAX_TOKENS=131072 \
  aidd-intern --model ollama/qwen-long "your prompt"
```

如果你只做调研，优先选择上下文窗口较大的远程模型，并明确要求输出来源链接：

```bash
aidd-intern --domain-pack none --model openrouter/openai/gpt-5.2 \
  "请调研 X。要求：优先搜索最近 365 天资料；每个结论都给出链接；区分论文、官方文档和博客。"
```

## 项目结构

- `agent/`：异步 agent runtime、CLI 入口、上下文管理、工具路由、会话持久化、
  模型切换、内置工具和 domain packs。
- `backend/`：FastAPI 后端，负责 hosted session、auth、quota、dataset
  upload、KPI scheduling、REST/SSE/WebSocket API。
- `frontend/`：Vite + React + TypeScript + MUI Web App。
- `configs/`：CLI 和 frontend 共享默认配置，包括模型、domain pack、trace 和
  MCP server。
- `scripts/`：本地 dev launcher、ProteinMCP setup/run helper、KPI/SFT 工具和
  sandbox cleanup。
- `src/`：Node.js CLI package 源码，用于 smoke、integration 和 eval harness。
- `fixtures/`：Node CLI eval prompts。
- `tests/`：pytest 和 Node harness tests。
- `evals/protein_design/`：protein design benchmark scaffold。
- `docs/`：架构、上下文管理、多智能体协作、binder workflow 和 protein design
  domain pack 文档。

## 开发和测试

提交前建议运行：

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

如果格式检查失败：

```bash
uv run ruff format .
uv run ruff check .
uv run ruff format --check .
```

前端改动：

```bash
cd frontend
npm run lint
npm run build
```

Node CLI package：

```bash
npm run build
npm run lint
npm test
npm pack --dry-run
```

Binder 和 MCP 相关的聚焦测试：

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider \
  tests/unit/test_binder_design_tool.py \
  tests/unit/test_mcp_startup.py \
  tests/unit/test_config.py \
  tests/unit/test_web_search_tool.py
```

Protein design 域包测试：

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider \
  tests/unit/test_protein_design_domain_pack.py
```

Protein design benchmark scaffold smoke test：

```bash
uv run python evals/protein_design/runner.py \
  --model test-model \
  --output /tmp/protein_design_eval_results.json
```

该命令会写临时结果到 `/tmp`，不要把 benchmark 输出提交到仓库。

## 会话追踪和分享

CLI session 可以自动上传到用户自己的 Hugging Face 私有 dataset，并使用
Claude Code JSONL 兼容格式，方便用 HF Agent Trace Viewer 查看 turns、tool
calls 和模型回答。

默认目标：

```text
{your-hf-username}/aidd-intern-sessions
```

CLI 内命令：

```text
/share-traces
/share-traces public
/share-traces private
```

关闭上传：

```json
{
  "share_traces": false
}
```

覆盖目标 repo：

```json
{
  "personal_trace_repo_template": "{hf_user}/my-custom-traces"
}
```

## GitHub 协作

- 不要提交 `.env`、token、权重、checkpoint、数据库或生成的大型结构批次。
- 代码改动优先通过 GitHub PR 合并，不直接推送部署分支。
- 多行 PR 描述建议使用 `gh pr edit <number> --body-file <file>`，避免 shell
  quoting 破坏 Markdown、环境变量或反引号。

## Cite AIDD-Intern

If you use `aidd-intern` in your work, please cite it by using the following
BibTeX entry or similar.

```bibtex
@Misc{aidd-intern,
  title =        {AIDD-Intern: an agent runtime for source-backed AI drug discovery research and binder workflows},
  author =       {Aksel Joonas Reedi, Henri Bonamy, Yoan Di Cosmo, Leandro von Werra, Lewis Tunstall},
  howpublished = {\url{https://github.com/huggingface/aidd-intern}},
  year =         {2026}
}
```
