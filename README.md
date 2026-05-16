<p align="center">
  <img src="frontend/public/smolagents.webp" alt="smolagents logo" width="160" />
</p>

<p align="center">
    <a href="https://github.com/huggingface/aidd-intern/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
    <a href="https://smolagents-aidd-intern.hf.space/"><img alt="Website" src="https://img.shields.io/website/https/smolagents-aidd-intern.hf.space.svg?down_color=red&down_message=offline&up_message=online"></a>
</p>

# AIDD-Intern

An ML intern that autonomously researches, writes, and ships good quality ML
related code using the Hugging Face ecosystem, with deep access to docs,
papers, datasets, cloud compute, and domain-specific AI drug discovery
workflows.

The project is organized as a reusable agent harness. The generic runtime owns
sessions, model calls, tool routing, approvals, persistence, telemetry, and UI
events; domain packs add specialized prompts and tools. The default domain pack
supports AIDD binder workflows, and the optional `protein_design` pack adds
protein binder generation, orthogonal validation, and ACE playbook memory.

## Project Layout

- `agent/` contains the reusable async agent runtime, CLI, context manager,
  model routing, session persistence/upload, tool router, built-in tools, roles,
  and domain packs.
- `backend/` contains the FastAPI web backend, hosted session manager, auth,
  quota checks, dataset uploads, KPI scheduler, and REST/SSE/WebSocket routes.
- `frontend/` contains the Vite + React + TypeScript + MUI web app, including
  the multi-session chat UI, AI SDK transport, persisted session state, and tool
  trace rendering.
- `configs/` contains the CLI and web agent defaults, including model,
  domain-pack, trace, and MCP server configuration.
- `scripts/` contains the local dev launcher, ProteinMCP setup/launch helpers,
  KPI/SFT utilities, sandbox cleanup, and local launcher installer.
- `tests/` contains pytest unit and integration tests; `evals/protein_design/`
  contains the protein-design benchmark scaffold.
- `docs/` contains architecture, context management, multi-agent, and
  protein-design domain-pack notes.

## Quick Start

### Installation

```bash
git clone git@github.com:huggingface/aidd-intern.git
cd aidd-intern
uv sync --extra dev
uv tool install -e .
```

#### That's it. Now `aidd-intern` works from any directory:

```bash
aidd-intern
```

Create a `.env` file in the project root (or export these in your shell):

```bash
ANTHROPIC_API_KEY=<your-anthropic-api-key> # if using anthropic models
OPENAI_API_KEY=<your-openai-api-key> # if using openai models
OPENROUTER_API_KEY=<your-openrouter-api-key> # if using openrouter/<model>
SILICONFLOW_API_KEY=<your-siliconflow-api-key> # if using siliconflow/<model>
AIDD_INTERN_DEFAULT_MODEL_ID=vllm/huihui-26b # replace suffix with /v1/models id if needed
VLLM_BASE_URL=http://192.168.4.6:8108 # vLLM OpenAI-compatible endpoint on peacock05
AIDD_INTERN_PROTEINMCP_HOME=~/.cache/aidd-intern/proteinmcp # local ProteinMCP installs
LOCAL_LLM_BASE_URL=http://localhost:8000 # shared fallback for local model prefixes
LOCAL_LLM_API_KEY=<optional-local-api-key> # optional shared local API key
HF_TOKEN=<your-hugging-face-token>
GITHUB_TOKEN=<github-personal-access-token>
```
If no `HF_TOKEN` is set, the CLI will prompt you to paste one on first launch
unless you start on a local model. To get a GITHUB_TOKEN follow the tutorial
[here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token).

### Local Web App

To start the local backend and frontend together from the repository root:

```bash
./scripts/dev.sh
```

The script resolves the repository path from its own location, installs
frontend dependencies with `npm ci` when `frontend/node_modules` is missing, and
starts both services. Use a full path to run it from another directory:

```bash
/path/to/aidd-intern/scripts/dev.sh
```

Default local endpoints:

- Frontend: `http://localhost:5173/`
- Backend health check: `curl -g http://[::1]:7860/api`
- Frontend proxy health check: `curl http://localhost:5173/api`

Run the services separately when debugging one side:

```bash
cd backend
uv run python -m uvicorn main:app --host ::1 --port 7860
```

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` and `/auth` to `http://[::1]:7860`; `/api` also proxies
WebSocket traffic. Override the launcher defaults with
`AIDD_INTERN_BACKEND_HOST`, `AIDD_INTERN_BACKEND_PORT`,
`AIDD_INTERN_FRONTEND_HOST`, or `AIDD_INTERN_FRONTEND_PORT`.

To install a user-level launcher:

```bash
./scripts/install-local-launcher.sh
aidd-intern-dev
```

By default, this creates `~/.local/bin/aidd-intern-dev`. Make sure
`~/.local/bin` is in your `PATH`.

### Usage

**Interactive mode** (start a chat session):

```bash
aidd-intern
```

**Headless mode** (single prompt, auto-approve):

```bash
aidd-intern "fine-tune llama on my dataset"
```

**Options:**

```bash
aidd-intern --model anthropic/claude-opus-4-7 "your prompt"   # requires ANTHROPIC_API_KEY
aidd-intern --model openai/gpt-5.5 "your prompt"              # requires OPENAI_API_KEY
aidd-intern --model openrouter/openai/gpt-5.2 "your prompt"   # requires OPENROUTER_API_KEY
aidd-intern --model siliconflow/deepseek-ai/DeepSeek-V4-Flash "your prompt" # requires SILICONFLOW_API_KEY
aidd-intern --model ollama/llama3.1:8b "your prompt"
aidd-intern --model vllm/huihui-26b "your prompt"
aidd-intern --model vllm/meta-llama/Llama-3.1-8B-Instruct "your prompt"
aidd-intern --sandbox-tools "your prompt"                         # use HF Space sandbox tools
aidd-intern --max-iterations 100 "your prompt"
aidd-intern --no-stream "your prompt"
```

Run `aidd-intern` then `/model` to see the full list of suggested model ids
(Claude, GPT, HF-router models like MiniMax, Kimi, GLM, DeepSeek, and local
model prefixes).

**Local models:**

Local model support uses OpenAI-compatible HTTP endpoints through LiteLLM. The
agent does not load model weights directly from disk; start your inference
server first, then select it with a provider-specific model prefix:

```bash
aidd-intern --model ollama/llama3.1:8b "your prompt"
aidd-intern --model vllm/huihui-26b "your prompt"
aidd-intern --model vllm/meta-llama/Llama-3.1-8B-Instruct "your prompt"
```

Inside interactive mode, switch with `/model`:

```text
/model ollama/llama3.1:8b
/model lm_studio/google/gemma-3-4b
/model llamacpp/llama-3.1-8b-instruct
```

Supported local prefixes are `ollama/`, `vllm/`, `lm_studio/`, and
`llamacpp/`. Set `LOCAL_LLM_BASE_URL` and optional `LOCAL_LLM_API_KEY` to use
one shared local endpoint, or override a specific provider with its matching
`*_BASE_URL` / `*_API_KEY` variable, such as `OLLAMA_BASE_URL` or
`VLLM_API_KEY`. Provider-specific variables take precedence over the shared
local variables. Base URLs may include or omit `/v1`.

For a vLLM server, the suffix after `vllm/` must match one of the model ids
returned by the server's OpenAI-compatible `GET /v1/models` endpoint. If the
server was launched with `--served-model-name huihui-26b`, use
`AIDD_INTERN_DEFAULT_MODEL_ID=vllm/huihui-26b`; otherwise set it to the exact
returned id, for example `vllm/Qwen/Qwen3-Coder-30B-A3B-Instruct`.

Unknown local and OpenAI-compatible models default to a conservative 65,536
token context policy. The session context manager tightens compaction
thresholds, keeps fewer untouched turns, and truncates oversized messages for
65K models so long autonomous runs do not fail with provider context-window
errors. Override the detected window when your serving stack exposes a
different limit:

```bash
AIDD_INTERN_MODEL_MAX_TOKENS=32768 aidd-intern --model vllm/my-small-model
AIDD_INTERN_MODEL_MAX_TOKENS=131072 aidd-intern --model ollama/qwen-long
```

**ProteinMCP tools:**

The default CLI and web configs register ProteinMCP's BindCraft, BoltzGen, and PXDesign
MCP servers through local stdio launchers. They do not use Docker. Install the
local source repos and conda environments once:

```bash
scripts/setup-proteinmcp-local.sh all
```

The setup installs under `AIDD_INTERN_PROTEINMCP_HOME`, defaulting to
`~/.cache/aidd-intern/proteinmcp`. To install only one server, pass
`bindcraft_mcp`, `boltzgen_mcp`, or `pxdesign_mcp`. BoltzGen setup defaults to `--skip-models`
so it does not block on the model download prompt; set
`AIDD_INTERN_BOLTZGEN_SETUP_ARGS=--download-models` if you want to fetch them
during setup. BindCraft setup downloads AlphaFold2 weights by default; set
`AIDD_INTERN_BINDCRAFT_SETUP_ARGS=--skip-weights` for a lighter setup that can
start the MCP but cannot run full designs until weights are installed. PXDesign
uses the official Conda installer by default; set `PXDESIGN_BIN` if you already
have a working PXDesign CLI elsewhere.

Do not commit model weights, checkpoints, databases, or generated structure
batches to GitHub. Keep large scientific assets in a local cache, shared
filesystem, object store, Hugging Face Hub repo, or container volume, then
point tools at them with environment variables. Common examples:

```bash
AIDD_INTERN_PROTEINMCP_HOME=/data/aidd-intern/proteinmcp
AIDD_INTERN_BINDCRAFT_SETUP_ARGS=--skip-weights
AIDD_INTERN_BOLTZGEN_SETUP_ARGS=--skip-models
PROTEIN_DESIGN_BINDCRAFT_CMD=/opt/bindcraft/run_bindcraft.sh
PROTEIN_DESIGN_BOLTZGEN_CMD=/opt/boltzgen/bin/boltzgen
PROTEIN_DESIGN_PXDESIGN_CMD=/opt/pxdesign/bin/pxdesign
```

If your cluster or container image already provides weights, set the command
variables to wrappers that export the tool-specific weight paths before
launching the underlying program.

The stdio launcher auto-clones missing MCP repos, but it does not run the heavy
`quick_setup.sh` step unless `AIDD_INTERN_PROTEINMCP_AUTO_SETUP=1` is set.

**Domain packs:**

AIDD-Intern defaults to the `aidd_binder` domain pack. The generic agent
runtime owns sessions, tool routing, approvals, persistence, and UI events; the
domain pack contributes binder-specific workflow tools and prompt policy.

Supported values:

- `aidd_binder`: default AIDD binder workflow pack. Registers `binder_design`,
  which creates project manifests, inspects generator outputs, and ranks
  candidates from BindCraft, BoltzGen, PXDesign, or compatible CSV metric files.
- `protein_design`: protein binder design pack. Registers generation tools for
  PXdesign, BoltzGen, and BindCraft; validation helpers for Chai-1, Protenix,
  and Foldseek; approval thresholds for expensive GPU runs; and an ACE playbook
  tool for campaign memory.
- `none`: generic runtime without domain-specific workflow tools.

Example config override:

```json
{
  "domain_pack": "protein_design"
}
```

Protein design details:

- `agent/domain_packs/protein_design/tools.py` wraps generator command
  boundaries.
- `agent/domain_packs/protein_design/validation.py` wraps Chai-1, Protenix, and
  Foldseek validation boundaries.
- `agent/domain_packs/protein_design/ace.py` implements ACE-style structured
  playbooks for incremental context engineering.
- `agent/roles/` and `agent/tools/role_handoff_tool.py` provide structured
  role handoffs for supervisor, researcher, executor, verifier, reviewer, and
  protein-design specialist roles.
- `evals/protein_design/` contains a headless benchmark scaffold and container
  environment templates.

Useful docs:

- `docs/context-management-guide.md`
- `docs/multi-agent-collaboration-guide.md`
- `docs/protein-design-domain-pack-guide.md`
- `docs/protein-design-optimization-roadmap.md`
- `docs/pd-l1-binder-design-report.md`
- `docs/aidd-intern-architecture-harness-guide.md`

**CLI tool runtime:**

By default, the CLI runs `bash`, `read`, `write`, and `edit` on your local
filesystem. To use HF Space sandbox tools instead, including `sandbox_create`,
opt in with `--sandbox-tools`:

```bash
aidd-intern --sandbox-tools "test this training script in a GPU sandbox"
aidd-intern --model llamacpp/ggml-org/gemma-3-1b-it-GGUF --sandbox-tools
```

Sandbox tool runtime requires `HF_TOKEN`, even when the selected model is local,
because it creates private HF Spaces. You can also make sandbox tools your CLI
default in `~/.config/aidd-intern/cli_agent_config.json`:

```json
{ "tool_runtime": "sandbox" }
```

Use the default local runtime when you want tools to inspect or edit files in
your checkout. Use sandbox runtime when you want the agent to create or replace
an HF Space sandbox, test code remotely, or request GPU sandbox hardware before
launching larger HF Jobs.

**Google Search:**

`web_search` uses Google Custom Search JSON API when these variables are set:

```bash
GOOGLE_SEARCH_API_KEY=...
GOOGLE_SEARCH_ENGINE_ID=...
```

Without those credentials, local development falls back to the built-in HTML
search backend and the tool output labels the provider as a fallback.

**AIDD biomedical sources:**

The built-in `aidd_bio` tool searches and fetches records from RCSB PDB,
AlphaFold DB, UniProt, and Foldseek. It supports bounded previews for
PDB/mmCIF/FASTA/JSON content so long structure files do not flood the model
context.

**Protein design execution boundaries:**

The protein-design pack keeps heavyweight scientific tooling outside the Python
agent process. Local runs expect tool commands to be available on `PATH` or
configured through environment variables:

```bash
PROTEIN_DESIGN_PXDESIGN_CMD=pxdesign
PROTEIN_DESIGN_BOLTZGEN_CMD=boltzgen
PROTEIN_DESIGN_BINDCRAFT_CMD=bindcraft
PROTEIN_DESIGN_CHAI1_CMD=chai1
PROTEIN_DESIGN_PROTENIX_CMD=protenix
PROTEIN_DESIGN_FOLDSEEK_CMD=foldseek
```

Generator wrappers inspect available GPU memory before launching heavy work.
When GPU headroom is low, the pack downscales sampling budgets or blocks the
run before allocation, returning a `gpu_plan` that explains the selected device,
free memory, and any adjustments. In environments without `nvidia-smi`, set a
test or scheduler-provided memory hint:

```bash
PROTEIN_DESIGN_GPU_FREE_MB=24000
```

For containerized runs, use the generation and validation Dockerfile scaffolds
under `evals/protein_design/environments/` and keep licensed packages such as
PyRosetta on approved internal distribution channels.

## Sharing Traces

Every session is auto-uploaded to your **own private Hugging Face dataset**
in [Claude Code JSONL format](https://huggingface.co/changelog/agent-trace-viewer),
which the HF Agent Trace Viewer auto-detects so you can browse turns, tool
calls, and model responses directly on the Hub.

By default the dataset is named `{your-hf-username}/aidd-intern-sessions` and is
**created private**. You can flip it to public from inside the CLI:

```bash
/share-traces            # show current visibility + dataset URL
/share-traces public     # publish (anyone can view)
/share-traces private    # lock it back down
```

You can also flip visibility from the dataset page on huggingface.co — the
agent honours whatever you set there for subsequent uploads.

To opt out entirely, set in your CLI config (e.g. `configs/cli_agent_config.json`
or `~/.config/aidd-intern/cli_agent_config.json`):

```json
{ "share_traces": false }
```

To override the destination repo, set:

```json
{ "personal_trace_repo_template": "{hf_user}/my-custom-traces" }
```

The shared `smolagents/aidd-intern-sessions` dataset is unrelated and only
receives anonymized telemetry rows used by the backend KPI scheduler.

## Supported Gateways

AIDD-Intern currently supports one-way notification gateways from CLI sessions.
These gateways send out-of-band status updates; they do not accept inbound chat
messages.

### Slack

Slack notifications use the Slack Web API to post messages when the agent needs
approval, hits an error, or completes a turn. Create a Slack app with a bot token
that has `chat:write`, invite the bot to the target channel, then set:

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C...
```

The CLI automatically creates a `slack.default` destination when both variables
are present. Optional environment variables for the env-only default:

```bash
AIDD_INTERN_SLACK_NOTIFICATIONS=false
AIDD_INTERN_SLACK_DESTINATION=slack.ops
AIDD_INTERN_SLACK_AUTO_EVENTS=approval_required,error,turn_complete
AIDD_INTERN_SLACK_ALLOW_AGENT_TOOL=true
AIDD_INTERN_SLACK_ALLOW_AUTO_EVENTS=true
```

For a persistent user-level config, put overrides in
`~/.config/aidd-intern/cli_agent_config.json` or point `AIDD_INTERN_CLI_CONFIG` at a
JSON file:

```json
{
  "messaging": {
    "enabled": true,
    "auto_event_types": ["approval_required", "error", "turn_complete"],
    "destinations": {
      "slack.ops": {
        "provider": "slack",
        "token": "${SLACK_BOT_TOKEN}",
        "channel": "${SLACK_CHANNEL_ID}",
        "allow_agent_tool": true,
        "allow_auto_events": true
      }
    }
  }
}
```

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         User/CLI                            │
└────────────┬─────────────────────────────────────┬──────────┘
             │ Operations                          │ Events
             ↓ (user_input, exec_approval,         ↑
      submission_queue  interrupt, compact, ...)  event_queue
             │                                          │
             ↓                                          │
┌────────────────────────────────────────────────────┐  │
│            submission_loop (agent_loop.py)         │  │
│  ┌──────────────────────────────────────────────┐  │  │
│  │  1. Receive Operation from queue             │  │  │
│  │  2. Route to handler (run_agent/compact/...) │  │  │
│  └──────────────────────────────────────────────┘  │  │
│                      ↓                             │  │
│  ┌──────────────────────────────────────────────┐  │  │
│  │         Handlers.run_agent()                 │  ├──┤
│  │                                              │  │  │
│  │  ┌────────────────────────────────────────┐  │  │  │
│  │  │  Agentic Loop (max 300 iterations)     │  │  │  │
│  │  │                                        │  │  │  │
│  │  │  ┌──────────────────────────────────┐  │  │  │  │
│  │  │  │ Session                          │  │  │  │  │
│  │  │  │  ┌────────────────────────────┐  │  │  │  │  │
│  │  │  │  │ ContextManager             │  │  │  │  │  │
│  │  │  │  │ • Message history          │  │  │  │  │  │
│  │  │  │  │   (litellm.Message[])      │  │  │  │  │  │
│  │  │  │  │ • Auto-compaction (170k)   │  │  │  │  │  │
│  │  │  │  │ • Session upload to HF     │  │  │  │  │  │
│  │  │  │  └────────────────────────────┘  │  │  │  │  │
│  │  │  │                                  │  │  │  │  │
│  │  │  │  ┌────────────────────────────┐  │  │  │  │  │
│  │  │  │  │ ToolRouter                 │  │  │  │  │  │
│  │  │  │  │  ├─ HF docs & research     │  │  │  │  │  │
│  │  │  │  │  ├─ HF repos, datasets,    │  │  │  │  │  │
│  │  │  │  │  │  jobs, papers           │  │  │  │  │  │
│  │  │  │  │  ├─ GitHub code search     │  │  │  │  │  │
│  │  │  │  │  ├─ Sandbox & local tools  │  │  │  │  │  │
│  │  │  │  │  ├─ Planning               │  │  │  │  │  │
│  │  │  │  │  └─ MCP server tools       │  │  │  │  │  │
│  │  │  │  └────────────────────────────┘  │  │  │  │  │
│  │  │  └──────────────────────────────────┘  │  │  │  │
│  │  │                                        │  │  │  │
│  │  │  ┌──────────────────────────────────┐  │  │  │  │
│  │  │  │ Doom Loop Detector               │  │  │  │  │
│  │  │  │ • Detects repeated tool patterns │  │  │  │  │
│  │  │  │ • Injects corrective prompts     │  │  │  │  │
│  │  │  └──────────────────────────────────┘  │  │  │  │
│  │  │                                        │  │  │  │
│  │  │  Loop:                                 │  │  │  │
│  │  │    1. LLM call (litellm.acompletion)   │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    2. Parse tool_calls[]               │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    3. Approval check                   │  │  │  │
│  │  │       (jobs, sandbox, destructive ops) │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    4. Execute via ToolRouter           │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    5. Add results to ContextManager    │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    6. Repeat if tool_calls exist       │  │  │  │
│  │  └────────────────────────────────────────┘  │  │  │
│  └──────────────────────────────────────────────┘  │  │
└────────────────────────────────────────────────────┴──┘
```

### Agentic Loop Flow

```
User Message
     ↓
[Add to ContextManager]
     ↓
     ╔═══════════════════════════════════════════╗
     ║      Iteration Loop (max 300)             ║
     ║                                           ║
     ║  Get messages + tool specs                ║
     ║         ↓                                 ║
     ║  litellm.acompletion()                    ║
     ║         ↓                                 ║
     ║  Has tool_calls? ──No──> Done             ║
     ║         │                                 ║
     ║        Yes                                ║
     ║         ↓                                 ║
     ║  Add assistant msg (with tool_calls)      ║
     ║         ↓                                 ║
     ║  Doom loop check                          ║
     ║         ↓                                 ║
     ║  For each tool_call:                      ║
     ║    • Needs approval? ──Yes──> Wait for    ║
     ║    │                         user confirm ║
     ║    No                                     ║
     ║    ↓                                      ║
     ║    • ToolRouter.execute_tool()            ║
     ║    • Add result to ContextManager         ║
     ║         ↓                                 ║
     ║  Continue loop ─────────────────┐         ║
     ║         ↑                       │         ║
     ║         └───────────────────────┘         ║
     ╚═══════════════════════════════════════════╝
```

## Events

The agent emits the following events via `event_queue`:

- `processing` - Starting to process user input
- `ready` - Agent is ready for input
- `assistant_chunk` - Streaming token chunk
- `assistant_message` - Complete LLM response text
- `assistant_stream_end` - Token stream finished
- `tool_call` - Tool being called with arguments
- `tool_output` - Tool execution result
- `tool_log` - Informational tool log message
- `tool_state_change` - Tool execution state transition
- `approval_required` - Requesting user approval for sensitive operations
- `turn_complete` - Agent finished processing
- `error` - Error occurred during processing
- `interrupted` - Agent was interrupted
- `compacted` - Context was compacted
- `undo_complete` - Undo operation completed
- `shutdown` - Agent shutting down

## Development

### Pre-commit Checks

Run Ruff and the test suite before every commit:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

If the format check fails, run `uv run ruff format .` and re-run the checks
before committing.

For frontend changes, also run:

```bash
cd frontend
npm run lint
npm run build
```

For domain-pack changes, also run:

```bash
uv run pytest tests/unit/test_protein_design_domain_pack.py
uv run pytest tests/unit
```

To smoke-test the protein-design evaluation scaffold:

```bash
uv run python evals/protein_design/runner.py \
  --model test-model \
  --output /tmp/protein_design_eval_results.json
```

CI runs `uv sync --locked --extra dev`, Ruff, Ruff format check, and
`uv run pytest` on Python 3.12.

### Code Boundaries

- Generic agent runtime behavior belongs in `agent/core/`.
- Domain prompts and tools belong in `agent/domain_packs/<name>/`.
- CLI behavior belongs in `agent/main.py`; hosted web-session orchestration
  belongs in `backend/session_manager.py`.
- Backend route changes generally belong under `backend/routes/`.
- Frontend event transport and message conversion belong under
  `frontend/src/lib/`; persistent UI/session state belongs under
  `frontend/src/store/`; reusable UI belongs under `frontend/src/components/`.
- Long-running scientific or GPU workloads should stay behind subprocess, MCP,
  container, sandbox, or HF Jobs boundaries rather than importing heavy runtime
  stacks into the FastAPI process.
- When changing shared MCP, model, trace, or domain defaults, keep
  `configs/cli_agent_config.json` and `configs/frontend_agent_config.json`
  aligned unless the difference is intentional.

### Adding Built-in Tools

Edit `agent/core/tools.py`:

```python
def create_builtin_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="your_tool",
            description="What your tool does",
            parameters={
                "type": "object",
                "properties": {
                    "param": {"type": "string", "description": "Parameter description"}
                },
                "required": ["param"]
            },
            handler=your_async_handler
        ),
        # ... existing tools
    ]
```

### Adding or Updating Domain Packs

Domain-specific code should live under `agent/domain_packs/<name>/`. A domain
pack should expose its tools through `agent/domain_packs/__init__.py` so the
generic `ToolRouter` can load them when `Config.domain_pack` matches.

Keep these boundaries intact:

- generic runtime behavior belongs in `agent/core/`;
- domain prompts and domain tools belong in `agent/domain_packs/`;
- long-running scientific or GPU workloads should stay behind subprocess,
  container, MCP, or HF Jobs boundaries;
- benchmark tasks and environment scaffolds belong in `evals/<domain>/`.

### Adding MCP Servers

Edit `configs/cli_agent_config.json` for CLI defaults, or
`configs/frontend_agent_config.json` for web-session defaults:

```json
{
  "model_name": "anthropic/claude-sonnet-4-5-20250929",
  "mcpServers": {
    "your-server-name": {
      "transport": "http",
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${YOUR_TOKEN}"
      }
    }
  }
}
```

Note: Environment variables like `${YOUR_TOKEN}` are auto-substituted from `.env`.

## Cite aidd-intern
If you use `aidd-intern` in your work, please cite it by using the following BibTeX entry or similar.
```bibtex
@Misc{aidd-intern,
  title =        {aidd-intern: an agent that autonomously researches, writes, and ships good quality ML related code using the Hugging Face ecosystem},
  author =       {Aksel Joonas Reedi, Henri Bonamy, Yoan Di Cosmo, Leandro von Werra, Lewis Tunstall},
  howpublished = {\url{https://github.com/huggingface/aidd-intern}},
  year =         {2026}
}
```
