# Agent Notes

## Project Shape

- `agent/`: reusable async agent runtime, CLI entrypoint, context management,
  tool routing, session persistence/upload, model switching, workflows, and
  built-in tools.
- `backend/`: FastAPI web backend. It owns hosted sessions, auth, quotas,
  dataset uploads, KPI scheduling, and the REST/SSE/WebSocket API used by the UI.
- `scripts/`: local dev launcher, ProteinMCP launch/setup helpers, KPI/SFT
  utilities, sandbox cleanup, and backlog tooling.
- `tests/`: pytest unit and integration tests.
- `evals/protein_design/`: protein-design benchmark scaffold.
- `fixtures/`: evaluation test prompts for the CLI harness.
- `docs/`: architecture, context-management, multi-agent, and workflow
  design notes.
- `configs/`: shared CLI defaults. Keep `cli_agent_config.json` updated.
- `agent/main.py` owns the CLI/TUI entrypoint; `agent/utils/terminal_display.py`
  owns terminal rendering; `agent/core/agent_loop.py` owns the runtime loop and
  session startup.

## Setup

- Python uses `uv`; install project dependencies with `uv sync --extra dev`.
- Install the editable CLI when needed with `uv tool install -e .`.
- Keep local secrets in root `.env` or shell exports. Common variables:
  `HF_TOKEN`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `OPENROUTER_API_KEY`, `SILICONFLOW_API_KEY`,
  `AIDD_INTERN_DEFAULT_MODEL_ID`, `LOCAL_LLM_BASE_URL`,
  `AIDD_INTERN_PROTEINMCP_HOME`, `AIDD_INTERN_ENABLE_PROTEINMCP`, and
  `AIDD_INTERN_TUI_TYPEWRITER`.
- Do not commit tokens, generated traces, model weights, checkpoints, databases,
  or generated structure batches.

## Local Dev Servers

- Preferred all-in-one launcher: `./scripts/dev.sh`. It starts the backend.
- Backend only: from `backend/`, run
  `uv run python -m uvicorn main:app --host ::1 --port 7860`.
- Backend health check: `curl -g http://[::1]:7860/api`.

Notes:

- `scripts/dev.sh` defaults to backend `::1:7860`. Override with `AIDD_INTERN_BACKEND_HOST`,
  `AIDD_INTERN_BACKEND_PORT`.

## CLI And Runtime

- Main command: `aidd-intern`.
- Headless usage: `aidd-intern "your prompt"`.
- Select models with `--model`, or set `AIDD_INTERN_DEFAULT_MODEL_ID`.
- Local model prefixes are OpenAI-compatible through LiteLLM; start the local
  inference server first, then use prefixes such as `ollama/`, `vllm/`,
  `lm_studio/`, or `llamacpp/`.
- The default workflow is `aidd_binder`. Supported workflows are
  `aidd_binder`, `protein_design`, and `none`.
- The default CLI tool runtime is local filesystem tools. Use `--sandbox-tools`
  when you want HF Space sandbox tools; that path requires `HF_TOKEN`.
- The default CLI/web configs list Hugging Face MCP and local ProteinMCP stdio
  launchers, but cold start filters them: Hugging Face MCP connects only when
  an HF token is available, and ProteinMCP starts only for the `protein_design`
  workflow or when `AIDD_INTERN_ENABLE_PROTEINMCP=1`.
- Hugging Face MCP should use the bearer-token `https://hf.co/mcp` endpoint.
  Avoid defaulting to `https://huggingface.co/mcp?login`; unauthenticated OAuth
  login attempts can add startup latency and print 401 tracebacks into the TUI.
- Use `scripts/setup-proteinmcp-local.sh all` for the heavy one-time
  ProteinMCP setup before enabling the `protein_design` workflow.
- The CLI startup path is intentionally split into a fast initialization pass
  and background preload work; keep cold-start work out of the prompt loop when
  possible.
- Tool schemas registered at startup should be static whenever possible. Avoid
  fetching remote OpenAPI/catalog data during startup; fetch it lazily inside
  the tool handler.
- Terminal animations should stay optional and non-blocking. Prefer buffered
  rendering and avoid per-character flush loops in the hot path.
- `AIDD_INTERN_BOOT_ANIMATION=1` re-enables the full boot animation when you
  want the slower visual startup.
- `AIDD_INTERN_TUI_TYPEWRITER=1` re-enables the slower Markdown typewriter
  rendering; the default TUI path should stay buffered.

## Development Checks

- Before every commit, run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

- If formatting fails, run `uv run ruff format .`, then re-run Ruff and tests.

- For workflow changes, include focused tests such as:

```bash
uv run pytest tests/unit/test_protein_design_workflow.py
uv run pytest tests/unit
```

- To smoke-test the protein-design evaluation scaffold:

```bash
uv run python evals/protein_design/runner.py \
  --model test-model \
  --output /tmp/protein_design_eval_results.json
```

- CI runs `uv sync --locked --extra dev`, `uv run ruff check .`,
  `uv run ruff format --check .`, and `uv run pytest` on Python 3.12.

## Code Boundaries

- Generic agent runtime behavior belongs in `agent/core/`.
- Domain prompts/tools belong in `agent/workflows/<name>/`.
- CLI behavior belongs in `agent/main.py`; web session orchestration belongs in
  `backend/session_manager.py`.
- Backend route changes generally belong under `backend/routes/`.
- Long-running scientific/GPU work should remain behind subprocess, MCP,
  container, sandbox, or HF Jobs boundaries. Do not import heavy GPU stacks into
  the FastAPI process.
- Environment substitutions like `${VAR}` are resolved from the environment and
  `.env` by the config loader.

## GitHub CLI

- For multiline PR descriptions, prefer
  `gh pr edit <number> --body-file <file>` over inline `--body` so shell
  quoting, `$` env-var names, backticks, and newlines are preserved correctly.

## GitHub PRs

- Open code changes as GitHub PRs first. Do not push code changes directly to
  the Hugging Face Space deployment branch or Space remote before the PR has
  been opened, reviewed, and merged, unless the user explicitly asks to bypass
  the PR flow.
- The repository has Claude review workflows. Treat generated review comments as
  feedback, but verify behavior locally before changing code.

## Hugging Face Space Deploys

- The Space remote is `space` and points to
  `https://huggingface.co/spaces/smolagents/aidd-intern`.
- Deploy GitHub `main` to the Space from the local `space-main` branch by
  merging `origin/main` into `space-main` with a single merge commit, then
  pushing `space-main:main` to the `space` remote.
- Keep the Space-only README frontmatter on `space-main`; `.gitattributes`
  should contain `README.md merge=ours` and the local repo config should include
  `merge.ours.driver=true`.
- Local dev commonly uses a personal `HF_TOKEN`, but the deployed Space uses HF
  OAuth tokens. When adding Hub features, make sure the Space README
  `hf_oauth_scopes` frontmatter and the backend OAuth request in
  `backend/routes/auth.py` include the scopes required by the Hub APIs being
  called. A feature can work locally with a broad PAT and still fail in
  production with 403s if OAuth scopes are missing; after changing scopes, users
  may need to log out and log in again to receive a fresh token.
- Recommended deploy flow:

```bash
git pull --ff-only origin main
git switch space-main
git config merge.ours.driver true
git merge --no-ff origin/main -m "Deploy $(date +%Y-%m-%d)" \
  -m "Co-authored-by: OpenAI Codex <codex@openai.com>"
git push space space-main:main
git switch main
```
