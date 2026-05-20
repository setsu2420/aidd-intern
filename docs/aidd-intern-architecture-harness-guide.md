# AIDD-Intern Architecture and Domain Harness Guide

Last reviewed: 2026-05-14

## Purpose

This document explains how AIDD-Intern is structured and how to reuse the same
architecture to build harnesses for other domains.

The main conclusion is that AIDD-Intern is less a single ML app than a reusable
agent harness with AI drug discovery workflow modules:

- a generic async agent runtime: session, context, model call loop, tool routing,
  approval, events, persistence, telemetry;
- AIDD workflow modules: biomedical database tools, prompts, research tools, Hub
  tools, sandbox, Jobs, dataset upload, Trackio, HF OAuth and Space deployment;
- two surfaces over the same runtime: local CLI and hosted web UI.

For a new domain harness, keep the runtime spine and add focused workflow
modules.

## Source Notes

I reviewed the local repository and external references. The user explicitly
asked for Google Search. In this environment, direct requests to
`https://www.google.com/search?...` can return challenge pages in automated
environments. The runtime now supports Google Custom Search JSON API when
`GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID` are configured, with the
legacy HTML parser retained only as a local development fallback.

External references used:

- Hugging Face smolagents API docs: agents inherit from `MultiStepAgent`; each
  step is thought, tool call, execution; `CodeAgent` uses Python tool calls and
  `ToolCallingAgent` uses JSON tool calls. Source:
  https://huggingface.co/docs/smolagents/en/reference/agents
- Hugging Face Hub Jobs docs: `run_job` runs compute Jobs on HF infrastructure,
  supports GPU flavors, volumes, UV script jobs, env, secrets, timeout and
  namespace. Source:
  https://huggingface.co/docs/huggingface_hub/main/en/package_reference/hf_api
- Hugging Face Docker Spaces docs: Docker Spaces use README YAML such as
  `sdk: docker` and `app_port: 7860`; runtime variables and secrets are exposed
  as environment variables; containers run as UID 1000. Source:
  https://huggingface.co/docs/hub/en/spaces-sdks-docker
- AgentBench paper: evaluates LLMs as agents in multi-turn interactive
  environments, with 8 environments and failure analysis around long-term
  reasoning, decision-making, and instruction following. Source:
  https://arxiv.org/abs/2308.03688
- SWE-bench paper: real GitHub issues plus repositories, requiring code edits
  and execution-environment interaction. Source:
  https://arxiv.org/abs/2310.06770
- GAIA paper: real-world assistant questions requiring reasoning,
  multimodality, web browsing, and tool-use proficiency. Source:
  https://arxiv.org/abs/2311.12983
- HELM paper: argues for broad scenario coverage and multi-metric evaluation
  beyond accuracy, including calibration, robustness, fairness, bias, toxicity,
  and efficiency. Source: https://arxiv.org/abs/2211.09110
- Inspect AI docs: a task is a recipe containing dataset, solver, scorer, and
  optional sandbox/approval/limits; agents can be top-level solvers, tools, or
  delegated components; scorers evaluate outputs against dataset targets and
  can inspect sandbox contents. Sources:
  https://inspect.aisi.org.uk/tasks.html,
  https://inspect.aisi.org.uk/agents.html,
  https://inspect.aisi.org.uk/scorers.html

## System Map

High-level dataflow:

```text
CLI / Web UI
  |
  | Operation: user_input, exec_approval, interrupt, undo, compact, new, resume, shutdown
  v
SessionManager or CLI submission loop
  |
  v
Session
  |-- ContextManager: messages, system prompt, compaction
  |-- ToolRouter: built-in tools + MCP tools
  |-- event_queue: streaming UI / CLI events
  |-- telemetry and persistence hooks
  v
agent_loop.run_agent()
  |
  | LLM call through LiteLLM
  | parse tool calls
  | approval gate
  | execute tools in parallel where safe
  | append tool results
  | repeat until no tool calls
  v
turn_complete / approval_required / error / interrupted events
```

Important local files:

- `agent/core/agent_loop.py`: main iteration loop, LLM retries, tool execution,
  approval handling, continuation guards, interrupt cleanup.
- `agent/core/session.py`: session state, event emission, trace upload,
  auto-save, model switching, notification fanout.
- `agent/context_manager/manager.py`: system prompt rendering, message history,
  token budget, compaction, dangling tool-call repair.
- `agent/core/tools.py`: `ToolSpec`, `ToolRouter`, built-in tool registration,
  MCP registration, tool schema conversion.
- `agent/main.py`: CLI and headless entrypoints.
- `backend/session_manager.py`: hosted multi-session orchestration, lazy
  restoration, SSE broadcasting, persistence snapshots, sandbox cleanup.
- `backend/routes/agent.py`: REST/SSE API for sessions, chat, approval, uploads,
  interrupts, model switching, quota.
- `frontend/src/lib/sse-chat-transport.ts`: converts backend SSE events to
  Vercel AI SDK `UIMessageChunk`s.
- `frontend/src/hooks/useAgentChat.ts`: per-session chat hook, hydration,
  reconnection, approval flow, side-channel UI state.

## Runtime Spine

### 1. Operation Queue

The runtime treats every user or UI action as an operation. The shared enum is
in `agent/core/session.py`:

- `USER_INPUT`
- `EXEC_APPROVAL`
- `INTERRUPT`
- `UNDO`
- `COMPACT`
- `NEW`
- `RESUME`
- `SHUTDOWN`

The CLI creates `Submission` records in `agent/main.py`; the web backend mirrors
the same structure in `backend/session_manager.py`. This is the first reusable
harness seam: a new UI can drive the same runtime if it can enqueue these
operations and consume events.

### 2. Session

`Session` owns all state needed for one agent conversation:

- identity: `session_id`, `user_id`, `hf_username`, `hf_token`;
- runtime config: selected model, stream flag, local/sandbox mode;
- memory: `ContextManager`;
- tools: `ToolRouter`;
- execution state: cancellation flag, pending approval, active sandbox, running
  HF job ids, current plan;
- observability: logged events, turn count, auto-save heartbeat, notification
  destinations;
- hosted-policy state: session-scoped auto approval and cost cap.

The critical design choice is that `Session.send_event()` is the single event
emission path. It logs the event, optionally persists it, puts it on the queue,
triggers notifications, and fires heartbeat saves. A new domain harness should
preserve this central event path, because it makes UI replay, telemetry, and
debugging possible.

### 3. ContextManager

`ContextManager` renders `agent/prompts/system_prompt_v3.yaml` through Jinja,
inserts tool count and HF user context, and stores `litellm.Message` history.

Key behavior:

- It tracks the model input-token ceiling via LiteLLM model metadata.
- It compacts at 90% of the model window.
- It preserves the system prompt, the first user task, and recent messages.
- It truncates oversized preserved messages before compaction.
- It repairs dangling assistant tool calls by inserting stub tool results.

For other domains, this is where the domain system prompt belongs. The harness
should not scatter domain rules across tool handlers and UI components unless
the rule is truly tool-specific.

### 4. Agent Loop

`Handlers.run_agent()` in `agent/core/agent_loop.py` is the heart of AIDD-Intern.
The loop is:

1. Add the user message, if present.
2. Emit `processing`.
3. Compact if needed.
4. Inject doom-loop or malformed-tool recovery prompts if needed.
5. Send messages and tool specs to `litellm.acompletion`.
6. Stream assistant chunks to events.
7. Parse tool calls.
8. Add the assistant message with tool calls to context.
9. Split tool calls into approval-required and auto-executable.
10. Execute non-approval tools concurrently.
11. Emit `approval_required` and pause if sensitive tools need human approval.
12. Append tool outputs to context.
13. Repeat until the model returns no tool calls.
14. Emit `turn_complete`, `error`, or `interrupted`.

The implementation deliberately has safety rails:

- LLM retry/backoff for transient and rate-limit errors.
- Context overflow handling with compaction.
- Invalid reasoning-effort healing.
- Anthropic thinking-signature healing.
- Output-truncation recovery.
- Malformed tool-call recovery.
- A no-tool continuation guard when the current plan still has unfinished
  items.
- Interrupt cleanup for active sandbox processes and running HF Jobs.

For a new harness, keep this loop unless the target domain requires a different
control policy. Most domains need different tools and prompts, not a different
loop.

## Tool System

### ToolRouter Contract

`ToolRouter` registers `ToolSpec` objects:

```python
ToolSpec(
    name="tool_name",
    description="What the tool does",
    parameters={... JSON schema ...},
    handler=async_handler,
)
```

It exposes OpenAI-style tool specs to the LLM and dispatches tool calls to
either:

- built-in async handlers; or
- FastMCP tools loaded from configured MCP servers.

The router blocks a few MCP names (`hf_jobs`, `hf_doc_search`, `hf_doc_fetch`,
`hf_whoami`) so remote MCP cannot shadow core tools.

### Built-in Tool Families

The current built-in tool registry includes these categories in `agent/core/tools.py`:

- research sub-agent: `research`;
- HF docs/API: `explore_hf_docs`, `fetch_hf_docs`, `find_hf_api`;
- papers: `hf_papers`;
- web search: `web_search`;
- datasets: `hf_inspect_dataset`;
- planning and notification: `plan_tool`, `notify`;
- compute: `hf_jobs`;
- Hub repositories: `hf_repo_files`, `hf_repo_git`;
- GitHub examples/code: `github_find_examples`, `github_list_repos`,
  `github_read_file`;
- execution substrate: local tools or sandbox tools.

Execution substrate is selected by `tool_runtime`:

- CLI defaults to local mode via `configs/cli_agent_config.json`; tools are
  `bash`, `read`, `write`, `edit` against the user's filesystem.
- Web sessions default to sandbox mode; a private `cpu-basic` HF Space sandbox
  is preloaded and `bash/read/write/edit` operate inside that sandbox.

### Approval Boundary

Approval is not a UI feature; it is runtime policy in `agent/core/agent_loop.py`.
The default approval targets are:

- `sandbox_create` when requesting non-default hardware;
- `hf_jobs` run/uv operations, especially GPU jobs;
- all scheduled HF jobs, always manual;
- `hf_repo_files` upload/delete;
- destructive `hf_repo_git` operations;
- repo creation and selected uploads.

The hosted web UI adds session-level auto-approval with a dollar cap. Scheduled
jobs still require manual approval even in YOLO mode.

For a new domain, define approval at the tool-operation layer, not the tool-name
layer only. Example: a finance harness might auto-approve read-only market data
queries but require manual approval for order placement, account mutation, or
paid data acquisition.

## Workflow Modules: What Is ML-Specific

The AIDD-Intern specialization is concentrated in these places:

- `agent/prompts/system_prompt_v3.yaml`: ML workflow policy, literature-first
  behavior, data audit, Trackio, hardware sizing, HF Jobs preflight.
- `agent/tools/research_tool.py`: a research sub-agent prompt optimized for ML
  literature, HF datasets, TRL/Transformers docs, and code recipes.
- `agent/tools/papers_tool.py`: paper search, citation graph, paper reading,
  dataset/resource discovery.
- `agent/tools/dataset_tools.py`: HF dataset inspection.
- `agent/tools/jobs_tool.py`: HF Jobs execution, GPU flavors, job logs,
  scheduled jobs, Trackio dashboard wiring.
- `agent/tools/sandbox_tool.py`: HF Space sandbox lifecycle, hardware upgrades,
  Trackio secrets.
- `backend/dataset_uploads.py`: session-scoped dataset upload to private HF
  datasets.
- `backend/routes/auth.py` and `backend/dependencies.py`: HF OAuth scopes and
  token propagation.
- `scripts/build_kpis.py`: AIDD-Intern product and reliability KPIs.

Everything above is a candidate replacement area for a non-ML domain harness.

## Frontend Architecture

The frontend is a React/Vite/MUI app using the Vercel AI SDK. It is not just a
chat transcript; it is a multi-session control surface for a long-running
agent.

Core pieces:

- `frontend/src/App.tsx`: top-level layout and background auth check.
- `frontend/src/components/Layout/AppLayout.tsx`: app shell, sidebars, session
  orchestration.
- `frontend/src/components/SessionChat.tsx`: one mounted chat per session; only
  the active session renders visible UI, but background sessions keep handling
  events.
- `frontend/src/hooks/useAgentChat.ts`: connects AI SDK chat state with backend
  session state, reconnects after refresh/sleep, hydrates messages from backend,
  handles approval and dataset-upload refresh.
- `frontend/src/lib/sse-chat-transport.ts`: maps backend event types to AI SDK
  stream chunks and side-channel callbacks.
- `frontend/src/store/sessionStore.ts`: persisted sidebar session metadata.
- `frontend/src/store/agentStore.ts`: per-session UI state outside message
  history: panel, plan, tool status, edited scripts, job URLs, Trackio iframe
  config, quota dialogs.

Important frontend pattern: message streaming and tool traces are separate
channels. Assistant text becomes AI SDK chunks; non-text events update side
panels and stores. A new domain should keep this split. It lets domain-specific
artifacts appear in a right panel without corrupting chat history.

## Backend Architecture

The backend is FastAPI plus a long-lived in-process session manager.

Startup in `backend/main.py`:

- loads `.env`;
- starts `session_manager`;
- starts in-process KPI scheduler;
- mounts API routers;
- serves built frontend from `static/` in production.

Routes in `backend/routes/agent.py`:

- health and model config;
- session create/restore/list/get/delete;
- session model switching;
- chat via `POST /api/chat/{session_id}` returning SSE;
- event replay via `GET /api/events/{session_id}`;
- approval via `/api/approve`;
- interrupt/undo/truncate/compact/shutdown;
- dataset upload;
- quota and jobs-access metadata;
- feedback telemetry.

`SessionManager` in `backend/session_manager.py`:

- enforces global and per-user session capacity;
- creates per-session queues, ToolRouter, Session, and event broadcaster;
- starts each session task;
- lazily restores sessions from Mongo;
- snapshots message history and metadata;
- cleans up active or persisted sandboxes;
- marks ended or deleted sessions.

The hosted architecture is intentionally stateful. It relies on durable
snapshots and event replay for restart recovery, but active execution lives in
process.

## Persistence and Observability

There are three persistence paths:

1. Local JSON backup in `session_logs/`, created by `Session.save_trajectory_local`.
2. Shared org dataset upload in row JSONL format, used for KPI rollups.
3. Per-user private dataset upload in Claude Code JSONL format for HF Agent
   Trace Viewer.

`agent/core/session_persistence.py` optionally uses MongoDB for hosted session
state:

- `sessions`: metadata and runtime state;
- `session_messages`: indexed message documents;
- `session_events`: append-only events with sequence numbers;
- `session_trace_messages`: append-only trace messages;
- `claude_quotas`, `pro_users`: product/account tracking.

Telemetry is event-native. `agent/core/telemetry.py` emits:

- `llm_call` with model, latency, finish reason, token usage, cache tokens and
  cost;
- `hf_job_submit` / `hf_job_complete`;
- `sandbox_create` / `sandbox_destroy`;
- `feedback`;
- Pro/credit conversion signals;
- heartbeat saves for long turns.

`scripts/build_kpis.py` rolls session events into hourly metrics, including
cost, cache hit ratio, tool success, HF jobs, sandbox usage, research calls,
distinct tools, and model distribution.

For other domain harnesses, treat every important domain action as an event.
Do not wait to infer business metrics from raw chat text.

## Deployment Shape

`Dockerfile` builds the frontend in a Node stage, then runs FastAPI in a Python
3.12 slim image with `uv`. It follows HF Docker Space requirements by creating
UID 1000 user `user`, setting `PORT`/`7860`, and serving the static frontend.

Local development notes from `AGENTS.md`:

- Frontend: `cd frontend && npm ci && npm run dev`.
- Backend: `cd backend && uv run uvicorn main:app --host ::1 --port 7860`.
- Vite proxies `/api` and `/auth` to backend.

## How AIDD-Intern Compares to Agent Frameworks

AIDD-Intern resembles a JSON tool-calling `MultiStepAgent` more than a code-agent.
The smolagents docs describe a multi-step agent as repeated thought plus tool
call plus execution, and distinguish `CodeAgent` Python actions from
`ToolCallingAgent` JSON calls. AIDD-Intern implements its own version around
LiteLLM, queues, SSE, approval, persistence, and HF-specific tooling rather
than importing smolagents' agent classes directly.

Compared with Inspect AI's evaluation abstraction, AIDD-Intern already has:

- solver: the agent loop plus tools;
- sandbox: local or HF Space sandbox;
- approval policy: runtime approval gate;
- logs: session events;
- limits: max iterations, context compaction, interrupt, quotas.

What AIDD-Intern does not currently have as a first-class evaluation harness is:

- dataset/task object model;
- deterministic sample runner;
- domain scorers;
- aggregate evaluator;
- reproducible per-sample sandbox setup/cleanup.

Those are the main additions needed for domain-specific benchmark harnesses.

## Lessons From Agent Benchmarks

External benchmark designs suggest these harness requirements:

- AgentBench emphasizes interactive environments, not single-turn QA. A useful
  harness should model state, actions, observations, and failures over multiple
  turns.
- SWE-bench shows the value of realistic tasks with executable verification.
  For software domains, the target should be "tests pass" or "artifact works",
  not "answer looks plausible".
- GAIA highlights real assistant tasks that require tool use, web browsing,
  reasoning, and sometimes multimodality. A domain harness should include tasks
  that cannot be solved from model memory alone.
- HELM argues for broad scenario coverage and multiple metrics. For agents,
  success rate alone is not enough; track cost, latency, safety, robustness,
  retries, approval burden, and tool failure.
- Inspect AI's task model is a useful mental template: dataset + setup +
  solver + sandbox + scorer + metrics + limits.

## Harness Abstraction for New Domains

A reusable domain harness can be defined with these interfaces:

```text
DomainHarness
  name
  system_prompt_template
  tool_registry
  approval_policy
  task_loader
  environment_factory
  scorer_registry
  artifact_contract
  telemetry_schema
  ui_artifact_renderers
```

Recommended Python shape:

```python
@dataclass
class HarnessSpec:
    name: str
    prompt_file: str
    tools: list[ToolSpec]
    mcp_servers: dict[str, MCPServerConfig]
    approval_policy: ApprovalPolicy
    artifact_types: list[str]
    telemetry_events: list[str]
```

The existing code can grow toward this by keeping AIDD-specific registration
behind focused workflow modules:

```text
agent/workflows/
  ml/
    prompt.yaml
    tools.py
    approval.py
    telemetry.py
  bio/
  finance/
  legal/
  robotics/
```

## What to Keep for Any Domain

Keep these pieces nearly unchanged:

- `Session` event path and trajectory format.
- `ContextManager` compaction and dangling tool-call repair.
- LiteLLM model abstraction and reasoning-effort probing.
- `ToolSpec`/`ToolRouter` contract.
- Operation queue.
- Approval-required pause/resume flow.
- SSE event protocol.
- Per-session frontend store model.
- Optional Mongo snapshots and event replay.
- Heartbeat save and final flush.
- KPI rollup pattern.

These are domain-agnostic infrastructure.

## What to Replace for a New Domain

Replace or parameterize these:

- System prompt and default workflow.
- Research sub-agent prompt.
- Tools and MCP servers.
- Approval rules.
- Artifact panel rendering.
- Dataset upload semantics.
- Sandbox image and environment setup.
- Domain telemetry events.
- KPI metrics.
- Evaluation task/scorer package.
- OAuth scopes and external service credentials.

## Domain Harness Checklist

### 1. Define the Domain Objective

Write down:

- primary user jobs;
- allowed resources;
- prohibited actions;
- expected artifacts;
- what "done" means;
- common failure modes;
- which actions need approval.

If "done" cannot be scored, the harness is not yet well-defined.

### 2. Build Domain Tools

For each tool, define:

- JSON schema with strict `additionalProperties: false` where practical;
- idempotency expectations;
- success/failure output shape;
- max output size and truncation strategy;
- whether it mutates external state;
- cost estimate if paid;
- event types emitted;
- artifact metadata for the UI.

Do not expose one giant "do everything" tool. Good harness tools should match
auditable domain actions.

### 3. Build Environment Isolation

Choose one:

- local filesystem tools for trusted CLI workflows;
- Docker or HF Space sandbox for untrusted code;
- domain simulator for repeatable tasks;
- remote API sandbox for paid/external systems.

Each environment should support:

- setup;
- action execution;
- observation;
- teardown;
- logs;
- artifact extraction;
- scoring access.

### 4. Build Scorers

Use multiple scorers:

- task success: exact match, tests pass, API state reached, target artifact
  produced;
- process quality: no prohibited tools, no hidden substitution, required
  approvals observed;
- cost and latency;
- robustness across retries/seeds;
- human-review rubric where deterministic scoring is impossible.

For code or data domains, prefer executable scorers over model-graded text.

### 5. Add Domain Telemetry

Add event types for the domain's core lifecycle. Examples:

- `case_loaded`
- `domain_tool_submit`
- `domain_tool_complete`
- `artifact_created`
- `verification_passed`
- `verification_failed`
- `policy_blocked`
- `human_review_required`

Then add KPI rollups beside `scripts/build_kpis.py`.

### 6. Add UI Artifact Panels

Map tool events to side-panel renderers:

- code/script;
- logs;
- tables;
- images;
- structured JSON;
- diff/patch;
- map/timeline;
- domain-specific report.

Keep the chat for reasoning and status. Put inspection artifacts in panels.

## Suggested Migration Plan

### Phase 1: Isolate Workflow Modules

Goal: keep ML-specific behavior isolated without changing runtime behavior.

Changes:

- Create a dedicated workflow module for ML behavior.
- Move `system_prompt_v3.yaml` or add a domain prompt selector.
- Move built-in ML tool registration into the workflow module when it becomes
  large enough to justify the split.
- Keep `ToolRouter` API stable.

Validation:

- `uv run ruff check .`
- `uv run ruff format --check .`
- existing unit tests;
- local CLI starts and still lists same tools;
- web session still creates and receives `ready`.

### Phase 2: Make Approval Policy Pluggable

Goal: remove hard-coded ML/HF operations from the agent loop.

Changes:

- Add an `ApprovalPolicy` interface.
- Move `_base_needs_approval()` rules into ML pack policy.
- Keep universal policy fallback for unknown mutating tools.
- Preserve scheduled-job always-manual behavior in ML policy.

Validation:

- approval tests for `hf_jobs`, `sandbox_create`, repo upload/delete;
- new sample policy tests for a dummy domain.

### Phase 3: Add Evaluation Task Model

Goal: run agent harnesses over repeatable task suites.

Add:

```text
evals/
  harness/
    task.py
    runner.py
    environment.py
    scorer.py
    report.py
```

Task record:

```json
{
  "id": "task-001",
  "input": "...",
  "target": "...",
  "metadata": {},
  "setup": {},
  "scorers": ["exact", "artifact_exists", "policy"]
}
```

Runner flow:

1. create isolated session;
2. seed system prompt and task input;
3. run until terminal event or limits;
4. collect messages, events, artifacts;
5. score;
6. write JSONL result.

### Phase 4: Add Domain UI Extensions

Goal: let a new harness add side-panel renderers without editing every chat
component.

Add a registry:

```ts
type ArtifactRenderer = {
  eventType: string;
  canRender(data: unknown): boolean;
  toPanel(data: unknown): PanelData;
};
```

ML registers script/log/Trackio renderers; other domains register their own.

## Example: Building a Biomedical Data Harness

Keep:

- session loop;
- local/sandbox tools;
- research sub-agent pattern;
- approval flow;
- SSE UI;
- telemetry.

Replace:

- prompt: biomedical evidence, dataset privacy, citation requirements;
- tools: PubMed/PMC search, ontology lookup, clinical guideline fetch,
  BioPython utilities, protected dataset loader;
- approval: external API writes, PHI-like uploads, paid database access;
- environment: Docker image with bioinformatics packages;
- scorers: exact answer, citation validity, code execution, statistical
  correctness, policy violations;
- artifacts: evidence table, PRISMA-like flow, plots, notebook, report.

## Example: Building a Finance Research Harness

Keep:

- session loop and approval;
- event telemetry;
- model abstraction;
- task runner.

Replace:

- prompt: financial analysis policy, no personalized investment advice unless
  explicitly allowed, data recency requirements;
- tools: market data, filings search, factor model, backtester, portfolio
  simulator;
- approval: any trade/order, paid data, account mutation;
- environment: deterministic backtest container;
- scorers: target return/risk metric, reproducibility, data leakage checks,
  transaction cost inclusion, policy compliance;
- artifacts: charts, tables, portfolio weights, audit trail.

## Risk Areas in Current Architecture

- AIDD-specific prompts, tools, approval rules and
  UI behavior are spread across modules.
- The web backend is stateful; horizontal scaling would need shared execution
  ownership or a worker queue, not just Mongo snapshots.
- `web_search` requires Google Custom Search credentials for auditable Google
  results; without those credentials it explicitly reports a local development
  fallback provider in tool output.
- Tool concurrency is broad. New mutating tools must be designed for parallel
  execution or marked/handled as serial.
- Evaluation dependencies exist (`inspect-ai` optional extra), but there is no
  first-class eval runner yet.
- The frontend artifact rendering is useful but not plugin-like; adding many
  domains will make side-channel callbacks bulky unless a renderer registry is
  introduced.

## Quality Gates for New Harnesses

Before shipping a new domain harness:

- A single task can run headlessly to terminal state.
- A sample task suite can run repeatedly with isolated environments.
- At least one deterministic scorer exists.
- Sensitive operations require approval.
- Tool outputs are bounded and redact secrets.
- Artifacts are saved and linked from the transcript.
- Session replay works after page refresh.
- Interrupt cleans up external resources.
- KPI rollup includes success, failure, cost, latency, tool usage and approval
  burden.
- Domain prompt states what the agent must verify before ending.

## Minimal Implementation Template

```text
agent/workflows/<domain>/
  __init__.py
  prompt.yaml
  tools.py
  approval.py
  telemetry.py
  README.md

evals/<domain>/
  tasks.jsonl
  runner.py
  scorers.py
  environments/
    Dockerfile

frontend/src/domainRenderers/<domain>.ts
```

`tools.py`:

```python
def create_tools(local_mode: bool = False) -> list[ToolSpec]:
    return [
        # domain tools first, generic tools after
    ]
```

`approval.py`:

```python
class DomainApprovalPolicy:
    async def decide(self, tool_name: str, args: dict, session: Session) -> ApprovalDecision:
        ...
```

`runner.py`:

```python
async def run_task(task: HarnessTask, model: str) -> HarnessResult:
    session = create_isolated_session(model=model)
    await submit(task.input)
    await wait_for_terminal_event()
    return score(session, task)
```

## Final Takeaway

AIDD-Intern's durable asset is the agent harness: queue-driven sessions,
tool-calling loop, approval gates, sandbox/compute execution, event streaming,
persistence, and telemetry. The AIDD-specific behavior is substantial but
replaceable. To build other domain harnesses, do not fork the entire app. Add
focused workflow tools, approval policy, environment setup, scorers, and
artifact renderers.
