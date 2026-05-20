<p align="center">
  <a href="https://github.com/setsu2420/aidd-intern/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://smolagents-aidd-intern.hf.space/"><img alt="Website" src="https://img.shields.io/website/https/smolagents-aidd-intern.hf.space.svg?down_color=red&down_message=offline&up_message=online"></a>
</p>

<p align="center">
  <strong>English</strong> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a>
</p>

# AIDD-Intern

AIDD-Intern is an asynchronous agent runtime for AI drug discovery research and
binder/protein-design workflows. It separates LLM calls, context management,
tool routing, MCP integration, session tracing, the web backend, and AIDD
domain tools so the same project can run source-backed research on a laptop and
delegate heavier binder workflows to external compute when available.

AIDD-Intern does not load LLM weights inside the CLI or FastAPI process. It also
does not import heavy scientific stacks such as BindCraft, BoltzGen, PXDesign,
Chai-1, or Protenix into the web backend. Use remote LLM APIs or an
OpenAI-compatible local inference server for the model layer, and connect heavy
protein-design tools through MCP, subprocesses, containers, clusters, or
Hugging Face Jobs.

## Languages

- English: [README.md](README.md)
- 简体中文: [README.zh-CN.md](README.zh-CN.md)
- 日本語: [README.ja.md](README.ja.md)

## Contents

- [What It Does](#what-it-does)
- [Quick Start](#quick-start)
- [Model Configuration And Switching](#model-configuration-and-switching)
- [API Keys And Search](#api-keys-and-search)
- [CLI Usage](#cli-usage)
- [Web App](#web-app)
- [Tools And MCP](#tools-and-mcp)
- [Context Strategy](#context-strategy)
- [Startup Performance](#startup-performance)
- [Project Layout](#project-layout)
- [Development And Tests](#development-and-tests)
- [Session Traces](#session-traces)
- [Citation](#citation)

## What It Does

- Source-backed research: `research`, `web_search`, `literature_lookup`,
  `hf_papers`, Hugging Face docs, GitHub code search/read tools, and `aidd_bio`
  help gather current sources before implementation or scientific decisions.
- Real Google Search support: when `GOOGLE_SEARCH_API_KEY` and
  `GOOGLE_SEARCH_ENGINE_ID` are set, `web_search` uses Google Custom Search JSON
  API with freshness and date sorting options.
- Model switching: select models with `--model`, configure aliases in
  `configs/models.json`, and switch interactively with `/model`.
- Adaptive context windows: remote OpenAI-compatible providers are not pinned to
  a fixed 65k context. Local unknown models still use a conservative default
  unless overridden.
- AIDD binder workflows: `binder_design` is available as a normal built-in tool
  for campaign planning, manifest creation, output checks, candidate ranking,
  validation-gap tracking, and reusable skill-card export.
- Protein design extensions: PXDesign, BoltzGen, BindCraft, Chai-1, Protenix,
  Foldseek, and campaign memory tools are registered by default. Heavy local MCP
  launchers still require explicit setup and opt-in.
- Local CLI and web UI: the Python CLI runs interactive or headless sessions;
  the FastAPI + React app provides hosted browser sessions; the Node.js package
  contains smoke, integration, and evaluation harnesses.
- Session tracing: sessions can be saved as Claude Code compatible JSONL and
  uploaded to a private Hugging Face dataset for review.

## Quick Start

### Requirements

- Python 3.11+
- `uv`
- Git
- Node.js 22+ only when working on the frontend or Node CLI harness
- Conda/Mamba and GPU only for local PXDesign, BindCraft, or similar scientific
  tools

### Install The Python Runtime

```bash
git clone https://github.com/setsu2420/aidd-intern.git
cd aidd-intern
uv sync --extra dev
uv tool install -e .
```

Use the HTTPS URL above for first-time setup. The SSH form
`git@github.com:setsu2420/aidd-intern.git` only works after your GitHub account
has an SSH key with access to the repository. Run the `uv` commands from inside
`aidd-intern`, because `uv sync` and `uv tool install -e .` read this project's
`pyproject.toml`.

Run the agent:

```bash
aidd-intern
```

### Research Without A Local GPU

Use a remote model and ask for source-backed research when you only need code
reading, planning, or reports:

```bash
aidd-intern --model openrouter/openai/gpt-5.2 \
  "Research recent protein binder design tools. Prefer Google Search, cite sources, and include publication dates."
```

This keeps local filesystem tools, web search, paper/document/GitHub lookup, and
the binder/protein workflow tools available without starting heavy local MCP
servers.

## Model Configuration And Switching

The shared model catalog lives at [configs/models.json](configs/models.json).
It controls the default model, visible model list, aliases, providers, tiers,
and recommended entries for both CLI and web surfaces.

Set the default model with either environment variables or the catalog:

```bash
AIDD_INTERN_DEFAULT_MODEL_ID=siliconflow/deepseek-ai/DeepSeek-V4-Flash
AIDD_INTERN_MODELS_CONFIG=configs/models.json
```

Start with a specific model:

```bash
aidd-intern --model openai/gpt-5.5 "your prompt"
aidd-intern --model anthropic/claude-opus-4-6 "your prompt"
aidd-intern --model openrouter/openai/gpt-5.2 "your prompt"
aidd-intern --model siliconflow/deepseek-ai/DeepSeek-V4-Flash "your prompt"
```

Interactive model commands:

```text
/model list
/model status
/model 2
/model flash
/model openrouter/openai/gpt-5.2
/model ollama/llama3.1:8b
/model --global siliconflow/deepseek-ai/DeepSeek-V4-Flash
```

`/model <id|alias|number>` changes only the current session. `/model --global
<id|alias|number>` also writes the selected model back to `configs/models.json`
as the default for future sessions.

### Local OpenAI-Compatible Models

AIDD-Intern calls local models through LiteLLM-compatible OpenAI HTTP endpoints.
Start your own inference server first, then use provider prefixes:

```bash
aidd-intern --model ollama/llama3.1:8b "your prompt"
aidd-intern --model vllm/Qwen/Qwen3-Coder-30B-A3B-Instruct "your prompt"
aidd-intern --model lm_studio/google/gemma-3-4b "your prompt"
aidd-intern --model llamacpp/qwen3.6-35b-a3b-gguf "your prompt"
```

Common environment variables:

```bash
LOCAL_LLM_BASE_URL=http://localhost:8000
LOCAL_LLM_API_KEY=<optional-local-api-key>
OLLAMA_BASE_URL=http://localhost:11434
VLLM_API_KEY=<optional-vllm-key>
```

## API Keys And Search

Create a root `.env` file or export variables in your shell. Do not commit
tokens, model weights, checkpoints, databases, generated structures, or traces.

```bash
OPENAI_API_KEY=<your-openai-api-key>
ANTHROPIC_API_KEY=<your-anthropic-api-key>
OPENROUTER_API_KEY=<your-openrouter-api-key>
SILICONFLOW_API_KEY=<your-siliconflow-api-key>

GOOGLE_SEARCH_API_KEY=<google-custom-search-json-api-key>
GOOGLE_SEARCH_ENGINE_ID=<programmable-search-engine-id>
GOOGLE_API_KEY=<optional-google-api-key-alias>
GOOGLE_CSE_ID=<optional-google-cse-id-alias>

HF_TOKEN=<your-hugging-face-token>
GITHUB_TOKEN=<github-personal-access-token>
```

`web_search` behavior:

1. If both Google variables are set, it uses Google Custom Search JSON API.
2. `recent_days` sends `dateRestrict=dN`.
3. `sort_by_date=true` sends `sort=date`.
4. Without Google credentials, local development uses the built-in HTML search
   fallback and reports the provider in the result.
5. If Google credentials are configured but Google returns an error, fallback is
   disabled unless `AIDD_INTERN_ALLOW_WEB_SEARCH_FALLBACK=1` is set.

Useful links:

- Google Custom Search JSON API: https://developers.google.com/custom-search/v1/overview
- Google Programmable Search Engine: https://programmablesearchengine.google.com/
- OpenAI API keys: https://platform.openai.com/api-keys
- Anthropic Console: https://console.anthropic.com/
- OpenRouter API keys: https://openrouter.ai/settings/keys
- Hugging Face access tokens: https://huggingface.co/docs/hub/security-tokens
- GitHub personal access tokens: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens

Run the live Google Search test only when real credentials are available:

```bash
PYTHONDONTWRITEBYTECODE=1 AIDD_INTERN_LIVE_WEB_SEARCH_TESTS=1 \
  uv run pytest -p no:cacheprovider tests/integration/test_web_search_live.py -s
```

## CLI Usage

Interactive:

```bash
aidd-intern
```

Headless one-shot:

```bash
aidd-intern "Research current AlphaFold-style complex validation methods and cite sources."
```

Common options:

```bash
aidd-intern "research-only task"
aidd-intern "plan a binder campaign"
aidd-intern "run protein design tools"
aidd-intern --sandbox-tools "test this script in an HF Space sandbox"
aidd-intern --max-iterations 100 "long task"
aidd-intern --no-stream "disable streaming"
```

## Web App

Start backend and frontend together:

```bash
./scripts/dev.sh
```

Default URLs:

- Frontend: `http://localhost:5173/`
- Backend health: `curl -g http://[::1]:7860/api`
- Frontend proxy health: `curl http://localhost:5173/api`

Start them separately:

```bash
cd backend
uv run python -m uvicorn main:app --host ::1 --port 7860
```

```bash
cd frontend
npm ci
npm run dev
```

## Tools And MCP

Default config files:

- CLI: [configs/cli_agent_config.json](configs/cli_agent_config.json)
- Web: [configs/frontend_agent_config.json](configs/frontend_agent_config.json)

User-level CLI config:

```bash
~/.config/aidd-intern/cli_agent_config.json
```

Override the CLI config path:

```bash
AIDD_INTERN_CLI_CONFIG=/path/to/cli_agent_config.json
```

MCP startup is intentionally lazy:

- Hugging Face MCP uses `https://hf.co/mcp` and is skipped when `HF_TOKEN` is
  missing.
- ProteinMCP launchers are skipped unless `AIDD_INTERN_ENABLE_PROTEINMCP=1` is
  set.
- Remote OpenAPI/catalog data is not fetched during startup; tool handlers fetch
  it only when the tool is called.

Binder and protein-design tools are normal built-in tools. `binder_design`,
`run_pxdesign`, `run_boltzgen`, `run_bindcraft`, and
`protein_design_ace_playbook` are visible to the model without a separate
workflow selector. The heavy local launchers only start after explicit setup and
environment opt-in.

Install local ProteinMCP tools when needed:

```bash
scripts/setup-proteinmcp-local.sh all
scripts/setup-proteinmcp-local.sh bindcraft_mcp
scripts/setup-proteinmcp-local.sh boltzgen_mcp
scripts/setup-proteinmcp-local.sh pxdesign_mcp
```

Run one local MCP server:

```bash
scripts/run-proteinmcp-local.sh bindcraft_mcp
scripts/run-proteinmcp-local.sh boltzgen_mcp
scripts/run-proteinmcp-local.sh pxdesign_mcp
```

## Context Strategy

Context size is model-aware:

- Known remote models use provider/catalog metadata when available.
- Unknown local models default to a conservative 65,536-token policy.
- Remote OpenAI-compatible models are not forced into the local 65k policy.
- Compaction runs before the model is likely to exceed its context window.

Overrides:

```bash
AIDD_INTERN_FORCE_MODEL_MAX_TOKENS=1000000
AIDD_INTERN_LOCAL_MODEL_MAX_TOKENS=131072
SILICONFLOW_MODEL_MAX_TOKENS=1000000
OPENROUTER_MODEL_MAX_TOKENS=1048576
```

## Startup Performance

The CLI startup path is split into a fast banner/config phase and deferred
runtime loading. Built-in tool schemas are registered without importing heavy
tool implementations, and handlers are loaded only when called. This keeps
packages such as `whoosh` and `nbconvert` out of the cold-start path for normal
local sessions.

To profile imports:

```bash
PYTHONPROFILEIMPORTTIME=1 uv run python -X importtime -m agent.main \
  --model siliconflow/deepseek-ai/DeepSeek-V4-Flash </dev/null
```

There is a regression test that starts a fresh Python subprocess, registers
local-mode tools, prints each step, and asserts that `docs_tools`,
`github_read_file`, `whoosh`, and `nbconvert` are still lazy:

```bash
uv run pytest tests/unit/test_mcp_startup.py -q
```

## Project Layout

- `agent/`: async agent runtime, CLI entrypoint, context management, model
  switching, tool routing, session persistence, and built-in tools.
- `backend/`: FastAPI backend for hosted sessions, auth, quotas, uploads, KPI
  scheduling, and REST/SSE/WebSocket APIs.
- `frontend/`: Vite + React + TypeScript + MUI web app.
- `configs/`: shared CLI/frontend defaults, model catalog, and MCP settings.
- `scripts/`: local dev launcher, ProteinMCP setup/run helpers, KPI/SFT tools,
  sandbox cleanup, and backlog utilities.
- `src/`: Node.js CLI package for smoke, integration, and evaluation harnesses.
- `fixtures/`: evaluation prompts for the Node CLI.
- `tests/`: Python and Node tests.
- `evals/protein_design/`: protein-design benchmark scaffold.
- `docs/`: architecture, context management, multi-agent, binder workflow, and
  protein-design guides.

## Development And Tests

Python checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Format when needed:

```bash
uv run ruff format .
uv run ruff check .
uv run ruff format --check .
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

Node CLI harness:

```bash
npm run build
npm run lint
npm test
npm pack --dry-run
```

Focused checks:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider \
  tests/unit/test_binder_design_tool.py \
  tests/unit/test_mcp_startup.py \
  tests/unit/test_config.py \
  tests/unit/test_web_search_tool.py

PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider \
  tests/unit/test_protein_design_workflow.py
```

Protein-design benchmark smoke test:

```bash
uv run python evals/protein_design/runner.py \
  --model test-model \
  --output /tmp/protein_design_eval_results.json
```

Do not commit benchmark outputs or generated temporary files.

## Session Traces

CLI sessions can be uploaded to a private Hugging Face dataset in Claude Code
compatible JSONL format.

Default target:

```text
{your-hf-username}/aidd-intern-sessions
```

CLI commands:

```text
/share-traces
/share-traces public
/share-traces private
```

Disable sharing:

```json
{
  "share_traces": false
}
```

Override the trace repo template:

```json
{
  "personal_trace_repo_template": "{hf_user}/my-custom-traces"
}
```

## Citation

If you use AIDD-Intern in your work, cite it with this BibTeX entry or similar:

```bibtex
@Misc{aidd-intern,
  title =        {AIDD-Intern: an agent runtime for source-backed AI drug discovery research and binder workflows},
  author =       {Aksel Joonas Reedi, Henri Bonamy, Yoan Di Cosmo, Leandro von Werra, Lewis Tunstall},
  howpublished = {\url{https://github.com/setsu2420/aidd-intern}},
  year =         {2026}
}
```
