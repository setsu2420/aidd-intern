# Protein Design Domain Pack Guide

Last reviewed: 2026-05-16

## Purpose

The `protein_design` domain pack extends the generic AIDD-Intern runtime with
protein binder design workflows. It keeps the existing Python architecture:

- the agent loop, session, approval, telemetry, and tool router stay in
  `agent/core/`;
- domain-specific logic lives under
  `agent/domain_packs/protein_design/`;
- benchmark scaffolding lives under `evals/protein_design/`;
- external heavy compute remains behind explicit CLI/container boundaries.

Do not move protein-design code into generic tool folders unless the behavior
is broadly reusable outside binder design.

For a concrete target-design memo, see
`docs/pd-l1-binder-design-report.md`. It follows the PD-L1 design-intelligence
requirements in `docs/step.md` and is intended as a template for future
target-specific binder campaigns.

## Runtime Integration

Enable the pack by setting:

```json
{
  "domain_pack": "protein_design"
}
```

The runtime path is:

```text
Config.domain_pack
  -> agent.domain_packs.create_domain_tools()
  -> agent.domain_packs.protein_design.tools.create_protein_design_tools()
  -> ToolRouter registers protein-design tools
  -> agent loop executes tools through the normal approval and event pipeline
```

The pack currently contributes these tools:

- `protein_design_ace_playbook`: maintains structured ACE context for long
  binder design campaigns.
- `run_pxdesign`: dispatches PXdesign backbone diffusion and sequence design.
- `run_boltzgen`: dispatches BoltzGen constraint-conditioned generation.
- `run_bindcraft`: dispatches BindCraft iterative optimization.

The default `aidd_binder` pack remains unchanged. Use `domain_pack="none"` for
a generic runtime with no domain-specific tools.

## File Map

```text
agent/domain_packs/protein_design/
├── __init__.py
├── ace.py          # ACE playbook: delta updates, counters, grow-and-refine
├── approval.py     # Protein-design compute approval thresholds
├── prompt.yaml     # Domain-specific workflow rules
├── telemetry.py    # Biological KPI summary helpers
├── tools.py        # Tool specs and generator subprocess boundaries
└── validation.py   # Chai-1, Protenix, and Foldseek orchestration

evals/protein_design/
├── tasks.jsonl
├── runner.py
└── environments/
    ├── Dockerfile.generation
    └── Dockerfile.validation
```

## Execution Boundaries

Generation and validation tools intentionally run as subprocess/container
boundaries. This keeps the Python agent lightweight and avoids importing GPU
frameworks into the web or CLI process.

For local execution, handlers expect commands such as `pxdesign`, `boltzgen`,
`bindcraft`, `chai1`, `protenix`, and `foldseek` to be available on `PATH`, or
configured through environment variables:

```bash
export PROTEIN_DESIGN_PXDESIGN_CMD="pxdesign"
export PROTEIN_DESIGN_BOLTZGEN_CMD="boltzgen"
export PROTEIN_DESIGN_BINDCRAFT_CMD="bindcraft"
export PROTEIN_DESIGN_CHAI1_CMD="chai1"
export PROTEIN_DESIGN_PROTENIX_CMD="protenix"
export PROTEIN_DESIGN_FOLDSEEK_CMD="foldseek"
```

For sandbox execution, the command builder uses Docker images named like:

```text
aidd-intern/protein-design-pxdesign:latest
aidd-intern/protein-design-boltzgen:latest
aidd-intern/protein-design-bindcraft:latest
```

The Dockerfiles in `evals/protein_design/environments/` are scaffolds. Add
licensed or internal packages such as PyRosetta through your approved
distribution channel.

## GPU-Aware Dispatch

Protein-design generators run a conservative GPU preflight before launching.
The preflight reads free VRAM with `nvidia-smi`; for tests or schedulers, set:

```bash
PROTEIN_DESIGN_GPU_FREE_MB=24000
```

Use comma-separated values for multiple GPUs:

```bash
PROTEIN_DESIGN_GPU_FREE_MB=12000,48000
```

The dispatcher selects the GPU with the most free memory and then:

- blocks execution when free VRAM is below the minimum safe threshold;
- downscales `num_samples` for PXdesign and BoltzGen when requested sampling is
  too large for available VRAM;
- downscales BindCraft iterations for long binders or low free memory;
- returns the `gpu_plan` in tool output so the agent can explain why it changed
  runtime shapes.

This does not prove a run can never OOM because real model memory depends on
target length, implementation details, CUDA fragmentation, and other processes.
It does prevent the agent from blindly launching obviously unsafe jobs and
gives the self-correction loop structured information for retry decisions.

## ACE Playbook Workflow

The ACE playbook is a structured JSON file that accumulates local lessons from
generation, validation, and failure logs.

Sections:

- `target_analysis`
- `generation_dispatch`
- `validation`
- `failure_modes`
- `reporting`

Expected use:

1. Initialize a playbook for a design campaign.
2. After each run, add small delta items with `section`, `content`, `feedback`,
   `source`, and `evidence`.
3. Let `apply_delta` merge duplicates, increment helpful/harmful counters, and
   prune low-value overflow bullets.
4. Render the playbook when the agent needs compact campaign memory.

Example delta item:

```json
{
  "section": "failure_modes",
  "content": "Reduce PXdesign samples and enable mixed precision after CUDA OOM.",
  "feedback": "helpful",
  "source": "run_pxdesign",
  "evidence": {
    "stderr_pattern": "CUDA out of memory"
  }
}
```

## Approval Policy

Protein-design generation can consume substantial GPU time. The core approval
policy requires human confirmation when:

- `run_pxdesign.num_samples > 200`
- `run_boltzgen.num_samples > 200`
- `run_bindcraft.iterations > 100`

Keep these thresholds conservative unless real deployment telemetry shows they
are too strict.

## Verification Commands

Run these before committing changes:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/unit/test_protein_design_domain_pack.py
```

For broader regression coverage:

```bash
uv run pytest tests/unit
```

For the evaluation scaffold:

```bash
uv run python evals/protein_design/runner.py \
  --model test-model \
  --output /tmp/protein_design_eval_results.json
```
