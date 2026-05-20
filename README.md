# AIDD-Intern

An Agent that autonomously researches, writes, and ships good quality ML related code using the Hugging Face ecosystem — with deep access to docs, papers, datasets, and cloud compute.

## Quick Start

### Installation

```bash
git clone git@github.com:huggingface/aidd-intern.git
cd aidd-intern
uv sync
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
AIDD_INTERN_DEFAULT_MODEL_ID=siliconflow/deepseek-ai/DeepSeek-V4-Flash
LOCAL_LLM_BASE_URL=http://localhost:8000 # shared fallback for local model prefixes
LOCAL_LLM_API_KEY=<optional-local-api-key> # optional shared local API key
HF_TOKEN=<your-hugging-face-token>
GITHUB_TOKEN=<github-personal-access-token> 
```
If no `HF_TOKEN` is set, the CLI will prompt you to paste one on first launch
unless you start on a local model. To get a GITHUB_TOKEN follow the tutorial
[here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token).

### Local Web App

To start the local backend and frontend together:

```bash
./scripts/dev.sh
```

The script resolves the repository path from its own location, so it also works
from any directory:

```bash
/path/to/aidd-intern/scripts/dev.sh
```

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

Run Ruff before every commit:

```bash
uv run ruff check .
uv run ruff format --check .
```

If the format check fails, run `uv run ruff format .` and re-run the checks
before committing.

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
