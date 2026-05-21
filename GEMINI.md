# AIDD-Intern

AIDD-Intern is an asynchronous agent runtime for AI drug discovery research and binder/protein-design workflows. It separates LLM calls, context management, tool routing, MCP integration, session tracing, the web backend, and AIDD domain tools.

## Project Overview

-   **Purpose:** Provide an autonomous agent system for drug discovery research, specifically targeting protein binder design and molecular ML.
-   **Architecture:**
    -   **Agent Runtime (Python):** Core logic, tool routing, and session management (`agent/`).
    -   **Web Backend (FastAPI):** Orchestrates sessions, authentication, and data persistence (`backend/`).
    -   **Frontend (React/TypeScript):** Interactive web interface (`frontend/`).
    -   **Node CLI (TypeScript):** Harness for smoke, integration, and evaluation tests (`src/`).
    -   **MCP Integration:** Connects heavy scientific tools (PXDesign, BindCraft, BoltzGen) via the Model Context Protocol.

## Tech Stack

-   **Languages:** Python 3.11+, TypeScript (Node.js 22+).
-   **Frameworks:** FastAPI (Backend), React + Vite (Frontend), Commander (Node CLI).
-   **Dependency Management:** `uv` (Python), `npm` (Node.js).
-   **AI/ML:** LiteLLM (Model routing), Hugging Face Hub/Jobs integration, Trackio (Monitoring).
-   **Testing:** `pytest` (Python), `vitest` (TypeScript), Ruff (Linting/Formatting).

## Getting Started

### Prerequisites

-   Python 3.11+ and `uv`.
-   Node.js 22+ and `npm`.
-   API keys for models (OpenRouter, OpenAI, Anthropic, or SiliconFlow).

### Installation (Source)

```bash
git clone https://github.com/setsu2420/aidd-intern.git
cd aidd-intern
uv sync --extra dev
uv tool install -e .
cp .env.example .env
```

### Environment Variables

Set these in your `.env` file:
- `AIDD_INTERN_DEFAULT_MODEL_ID`: e.g., `openrouter/openai/gpt-5.2`
- `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, etc.
- `HF_TOKEN`: For Hugging Face Hub/Jobs/MCP.
- `GOOGLE_SEARCH_API_KEY` & `GOOGLE_SEARCH_ENGINE_ID`: For real web search.
- `AIDD_INTERN_ENABLE_PROTEINMCP=1`: Opt-in for heavy scientific tools.

## Core Workflows

### 1. Agent Lifecycle
The agent follows a **Research -> Strategy -> Execution -> Validation** cycle.
- **Research First:** Always research landmark papers and current code examples before implementing ML code. Use `literature_lookup` and `aidd_bio`.
- **Autonomous Action:** The agent is designed to be fully autonomous, minimizing unnecessary confirmations.

### 2. AIDD Binder Design
The primary workflow for protein binder design:
1. **Preparation:** Research literature, download PDBs, crop structures, and identify hotspots.
2. **Design:** Create a project manifest, run generators (BindCraft, BoltzGen, etc.), and monitor jobs.
3. **Analysis:** Collect metrics, rank candidates, and export results.

### 3. Development Commands
- **Run Full Stack:** `./scripts/dev.sh` (Starts backend and frontend).
- **Run Python CLI:** `aidd-intern`.
- **Diagnostics:** `aidd-intern --doctor`.
- **Update (Source):** `scripts/update-local.sh` and `npm run update:local`.
- **Tests:**
  - Python: `uv run pytest`.
  - Node: `npm test`.
  - Linting: `uv run ruff check .` and `npm run lint` (in frontend).

## Project Structure

- `agent/`: Async agent runtime and built-in tools.
  - `core/`: Core loop, session, and tool routing.
  - `workflows/`: Domain-specific prompts and tools (e.g., `aidd_binder`).
- `backend/`: FastAPI backend routes and session management.
- `frontend/`: React frontend application.
- `src/`: TypeScript source for the Node CLI harness.
- `configs/`: Model catalog and agent configurations.
- `scripts/`: Utility scripts for dev, setup, and maintenance.
- `docs/`: Architecture guides and workflow documentation.
- `tests/`: Comprehensive test suites (unit, integration, harness).

## Engineering Standards

-   **Modularity:** Keep code modular to facilitate extension and maintenance.
-   **Type Safety:** Use Pydantic for Python and TypeScript/Zod for Node.js.
-   **Documentation:** Maintain up-to-date documentation in `docs/` and `README.md`.
-   **Security:** Never commit secrets, API keys, or large binary artifacts (model weights).
-   **Testing:** New features and bug fixes MUST be accompanied by tests.
-   **Agent Behavior:**
    - Always use `research` tools for ML tasks to avoid hallucinating outdated APIs.
    - Provide direct Hub URLs for models, datasets, and jobs.
    - Use Trackio for training monitoring and alert at critical decision points.
    - Ensure every response in autonomous mode includes at least one tool call.
