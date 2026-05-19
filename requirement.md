# AIDD Binder Design Requirements

## Goal

Build AIDD-Intern as a Binder Design first agent for drug-discovery workflows.
The current release must focus on:

- target intake and campaign planning,
- Binder Design tool configuration,
- project manifest creation,
- output inspection and ranking,
- reproducible verification,
- on-demand setup of optional generator or validation tools.

Other protein-design or broader ML capabilities can be added later.

## Current Scope

The default domain pack is `aidd_binder`.

The Binder Design tool must support:

- `plan_campaign`
- `create_project`
- `inspect_outputs`
- `rank_candidates`
- `export_skill`

The system must remain useful even when optional generator tools are not
installed. In that case it should still:

- plan binder campaigns,
- write manifests,
- inspect existing outputs,
- rank candidate CSVs,
- describe the missing toolchain clearly.

Completed campaigns should also be promotable into reusable skill cards so the
next similar project can reuse the same evidence-backed workflow instead of
rebuilding it from scratch.

## Tooling

Optional heavy tools are installed on demand with:

```bash
scripts/setup-proteinmcp-local.sh all
```

Individual launchers are handled by:

```bash
scripts/run-proteinmcp-local.sh bindcraft_mcp
scripts/run-proteinmcp-local.sh boltzgen_mcp
scripts/run-proteinmcp-local.sh pxdesign_mcp
```

If the machine does not have these tools yet, the agent should still be able to
research the missing steps, explain the gap, and continue with Binder Design
planning.

## Documentation Rules

- Remove legacy `ml-intern` framing from user-facing docs.
- Keep Binder Design as the first product surface.
- Keep the docs aligned with the current config, prompt, and tests.
- Prefer concise, file-backed instructions over narrative comparisons.

## Verification

Required checks for Binder-related changes:

```bash
npm test
uv run pytest tests/unit/test_binder_design_tool.py
uv run pytest tests/unit/test_mcp_startup.py
uv run pytest tests/unit/test_config.py
```

Run broader checks when prompts, docs, or startup behavior change:

```bash
npm run lint
npm run build
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
