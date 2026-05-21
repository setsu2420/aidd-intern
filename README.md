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
- [Local Updates](#local-updates)
- [Local Diagnostics](#local-diagnostics)
- [AIDD Preparation Stage](#aidd-preparation-stage)
- [Model Configuration And Switching](#model-configuration-and-switching)
- [API Keys And Search](#api-keys-and-search)
- [Tool Configuration](#tool-configuration)
- [CLI Usage](#cli-usage)
- [Web App](#web-app)
- [Tools And MCP](#tools-and-mcp)
- [Context Strategy](#context-strategy)
- [Startup Performance](#startup-performance)
- [Project Layout](#project-layout)
- [Development And Tests](#development-and-tests)
- [Session Traces](#session-traces)

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
- AIDD preparation stage: `aidd_prepare` creates a local preparation project,
  collects literature metadata, downloads RCSB PDB files, crops target
  structures, and ranks contact-derived hotspot residue candidates.
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

-   Python 3.11+
-   [uv](https://github.com/astral-sh/uv) (Fast Python package manager)
-   Node.js 22+ (Optional: only if you work on the frontend or Node harness)
-   Git (For source checkout)

### Installation

Follow the `ml-intern` style installation to set up the agent runtime:

```bash
# 1. Clone the repository
git clone https://github.com/setsu2420/aidd-intern.git
cd aidd-intern

# 2. Sync dependencies and install the CLI tool
uv sync --extra dev
uv tool install -e .

# 3. Configure environment
cp .env.example .env
```

After installation, the `aidd-intern` command will be available in your shell.

Before the first real LLM call, edit `.env` and set at least one API key. Run the diagnostic to verify your setup:

```bash
aidd-intern doctor
```

### Usage

**Interactive Mode:**

```bash
aidd-intern
```

**Headless Mode:**

```bash
aidd-intern "Research recent protein binder design tools. Prefer Google Search, cite sources."
```

**Configure LLM:**

```bash
aidd-intern configure-llm
aidd-intern configure-llm openrouter
```

## Local Updates

Update your local checkout and the installed CLI:

```bash
aidd-intern update
```

Use `--with-frontend` if you also need to refresh frontend dependencies:

```bash
aidd-intern update --with-frontend
```

For a dry run or to check version status:

```bash
aidd-intern update --dry-run
aidd-intern update --check
```

## Local Diagnostics

Run the doctor after setting up the source-checkout Python runtime, after
editing `.env`, or after updating:

```bash
aidd-intern --doctor
```

The diagnostic is read-only. It prints each step, checks Python, `git`, `uv`,
optional `npm`, config loading, the selected model's expected API key, Google
Search credentials, the GitHub version status, the update helper, optional
frontend dependencies, and the ProteinMCP opt-in flag.

This follows the same practical setup pattern used by Hermes Agent: install,
configure one provider, run a doctor-style check, then verify a simple chat
before enabling heavier tools.

## AIDD Preparation Stage

Before running binder generation from the source-checkout Python runtime,
complete the four local preparation tasks:

1. Literature research: collect papers, official pages, DOIs, PMIDs, preprint
   IDs, known binders, epitopes, and assay constraints with `literature_lookup`
   and `web_search`.
2. PDB download: fetch the selected experimental structure from RCSB PDB.
3. Structure cropping: keep the target chain or domain that downstream design
   tools should see.
4. Hotspot residue determination: rank target residues at the target/partner
   interface, then cross-check the candidates against literature or mutagenesis
   evidence.

The Python CLI can run the complete preparation pass after installation:

```bash
aidd-intern --prepare-aidd \
  --target-name "PD-L1" \
  --pdb-id 4ZQK \
  --target-chains A \
  --partner-chains B \
  --residue-ranges A:19-134 \
  --prep-project-dir runs/pd-l1-prep
```

This writes:

- `aidd_preparation_manifest.json`
- `literature/literature_sources.md`
- `structures/raw/<PDB_ID>.pdb`
- `structures/cropped/<PDB_ID>_<chains>_crop.pdb`
- `analysis/hotspots.json`
- `aidd_preparation_summary.md`

`aidd_prepare` is also available to the agent as a built-in tool with
`create_project`, `literature_research`, `download_pdb`, `crop_structure`,
`identify_hotspots`, and `run_preparation` operations. Hotspots are ranked from
non-hydrogen atom contacts across the requested target and partner chains; they
are useful preparation candidates, not experimental binding-energy proof.

## Model Configuration And Switching

The shared model catalog lives at [configs/models.json](configs/models.json).
It controls the default model, visible model list, aliases, providers, tiers,
and recommended entries for both CLI and web surfaces.

Set the default model with either environment variables or the catalog. New
users without a local inference server should choose a remote provider and set
the matching API key in `.env` first:

```bash
AIDD_INTERN_DEFAULT_MODEL_ID=openrouter/openai/gpt-5.2
AIDD_INTERN_MODELS_CONFIG=configs/models.json
```

The npm harness can print provider-specific setup steps without editing files:

```bash
aidd-intern configure-llm
aidd-intern configure-llm openrouter
aidd-intern configure-llm local
```

The configuration shape intentionally mirrors OpenClaw/Hermes-style setup:
choose one provider, set a model id, put the provider API key or local base URL
in `.env`, then run a doctor/check command before using the full workflow.

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
The CLI and backend load the root `.env` automatically.

Start from the checked-in template:

```bash
cp .env.example .env
```

```bash
# LLM providers. Set one or more according to your selected model.
OPENAI_API_KEY=<your-openai-api-key>
ANTHROPIC_API_KEY=<your-anthropic-api-key>
OPENROUTER_API_KEY=<your-openrouter-api-key>
SILICONFLOW_API_KEY=<your-siliconflow-api-key>

# Default model. This can also be overridden per command with --model.
AIDD_INTERN_DEFAULT_MODEL_ID=openrouter/openai/gpt-5.2
AIDD_INTERN_MODELS_CONFIG=configs/models.json

# Real Google Search. Both variables must be set for the Google provider.
GOOGLE_SEARCH_API_KEY=<google-custom-search-json-api-key>
GOOGLE_SEARCH_ENGINE_ID=<programmable-search-engine-id>

# Optional aliases also recognized by the search tool.
GOOGLE_API_KEY=<google-custom-search-json-api-key>
GOOGLE_CSE_ID=<programmable-search-engine-id>

# Hugging Face and GitHub tools.
HF_TOKEN=<your-hugging-face-token>
GITHUB_TOKEN=<github-personal-access-token>

# Local or LAN OpenAI-compatible inference servers.
LOCAL_LLM_BASE_URL=http://localhost:8000
LOCAL_LLM_API_KEY=<optional-local-api-key>
```

`web_search` behavior:

1. If both Google variables are set, it uses Google Custom Search JSON API.
2. `recent_days` sends `dateRestrict=dN`.
3. `sort_by_date=true` sends `sort=date`.
4. Without Google credentials, local development uses the built-in HTML search
   fallback and reports the provider in the result.
5. If Google credentials are configured but Google returns an error, fallback is
   disabled unless `AIDD_INTERN_ALLOW_WEB_SEARCH_FALLBACK=1` is set.

Google's current documentation says Custom Search JSON API requires both a
Programmable Search Engine ID and an API key. Google also announced that
Custom Search JSON API users must transition to an alternative solution by
January 1, 2027, so keep this dependency explicit in `.env`.

Useful links:

- Google Custom Search JSON API: https://developers.google.com/custom-search/v1/overview
- Google Programmable Search Engine: https://programmablesearchengine.google.com/
- OpenAI API keys: https://platform.openai.com/api-keys
- Anthropic Console: https://console.anthropic.com/
- OpenRouter API keys: https://openrouter.ai/settings/keys
- SiliconFlow quickstart: https://docs.siliconflow.cn/en/userguide/quickstart
- Hugging Face access tokens: https://huggingface.co/docs/hub/security-tokens
- GitHub personal access tokens: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- uv sync: https://docs.astral.sh/uv/concepts/projects/sync/
- uv tool install: https://docs.astral.sh/uv/concepts/tools/
- Git pull: https://git-scm.com/docs/git-pull

Run the live Google Search test only when real credentials are available:

```bash
PYTHONDONTWRITEBYTECODE=1 AIDD_INTERN_LIVE_WEB_SEARCH_TESTS=1 \
  uv run pytest -p no:cacheprovider tests/integration/test_web_search_live.py -s
```

## Tool Configuration

The tool surface is configured from the checked-in defaults plus a small set of
environment variables:

- CLI tool config: [configs/cli_agent_config.json](configs/cli_agent_config.json)
- Web tool config: [configs/frontend_agent_config.json](configs/frontend_agent_config.json)
- Override the CLI config path with `AIDD_INTERN_CLI_CONFIG=/path/to/cli_agent_config.json`
- Real Google Search in `web_search` requires both `GOOGLE_SEARCH_API_KEY` and
  `GOOGLE_SEARCH_ENGINE_ID` (or the aliases `GOOGLE_API_KEY` and
  `GOOGLE_CSE_ID`)
- Set `AIDD_INTERN_ALLOW_WEB_SEARCH_FALLBACK=1` to fall back to the local HTML
  search backend when Google returns an error
- Override the fallback search backend URL with `CLAWD_WEB_SEARCH_BASE_URL`
- `HF_TOKEN` enables Hugging Face MCP startup
- `AIDD_INTERN_ENABLE_PROTEINMCP=1` opts into local ProteinMCP launchers for
  the heavier generator tools
- `AIDD_INTERN_DISABLE_UPDATE_CHECK=1` suppresses read-only version checks in
  interactive startup and `aidd-intern --doctor`
- `binder_design` and `aidd_prepare` are built-in binder workflow tools and do
  not need separate MCP setup

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
