# Protein Design Optimization Roadmap

Last reviewed: 2026-05-16

## Architectural Principle

Keep the current Python runtime architecture. Optimize by improving boundaries,
observability, and deterministic domain logic rather than rewriting the agent
loop.

The stable seams are:

- `agent/core/tools.py` for tool registration;
- `agent/workflows/protein_design/tools.py` for generator dispatch;
- `agent/workflows/protein_design/validation.py` for validator dispatch;
- `agent/workflows/protein_design/ace.py` for campaign memory;
- `evals/protein_design/runner.py` for benchmark orchestration.

## Near-Term Optimizations

### 1. Structured Command Results

Current generation handlers return stdout/stderr plus a parsed hardware-error
summary. Extend this into a standard result schema:

```json
{
  "status": "completed | failed | needs_runtime_correction",
  "tool": "pxdesign",
  "command": ["..."],
  "outputs": {
    "metrics": "...",
    "structures": ["..."],
    "logs": ["..."]
  },
  "hardware_errors": {
    "cuda_oom": false,
    "suggested_correction": null
  }
}
```

This makes downstream validation and reporting independent of each generator's
native output layout.

### 2. Generator Output Manifests

Require each generator wrapper to write a manifest:

```text
outputs/
  pxdesign/
    run_manifest.json
    logs/
    candidates/
    metrics/
```

The manifest should include command, input target, interface residues,
container/image version, start/end timestamps, return code, and discovered
candidate paths.

### 3. Validation Queue

Do not validate every raw design when generators produce large batches. Add a
lightweight prefilter stage:

1. Parse generator metrics.
2. Keep top candidates by pLDDT, ipTM, interface score, clashes, and diversity.
3. Run Chai-1 and Protenix only on the prefiltered set.
4. Cluster passing candidates with Foldseek.

This reduces GPU validation cost and keeps the agent loop responsive.

### 3a. GPU-Aware Runtime Shapes

Generation wrappers now expose a conservative `gpu_plan` based on free VRAM.
Future work should replace the current heuristic constants with empirical
profiles collected per tool, target length, binder length, precision mode, and
GPU class. The desired long-term behavior is:

1. estimate memory before every heavy generation or validation run;
2. select the largest available GPU that satisfies the estimate;
3. downscale samples, batch size, or iterations before launch when safe;
4. refuse unsafe jobs before they hit CUDA OOM;
5. record the adjustment in ACE playbook `failure_modes` or `generation_dispatch`.

### 4. ACE Auto-Delta Hooks

After each generator or validator run, create ACE delta items automatically:

- CUDA OOM -> `failure_modes`
- low Chai-1/Protenix agreement -> `validation`
- successful interface hotspot strategy -> `target_analysis`
- Foldseek cluster collapse -> `generation_dispatch`

Keep the delta small and evidence-backed. Avoid adding generic protein design
advice that did not come from the current campaign.

### 5. Evaluation Metrics

Extend `evals/protein_design/runner.py` to produce:

- success rate at `ipTM > 0.8` and `pLDDT > 80`;
- Chai-1/Protenix agreement rate;
- Foldseek cluster count among passing candidates;
- GPU wall-clock estimates;
- number of self-corrections after OOM or failed validation.

## Medium-Term Optimizations

### 1. Protein Workflow Prompt Loading

The protein-design workflow has `prompt.yaml`, but the global context manager
still renders the main system prompt. A future improvement is to layer workflow
prompt text into the system prompt when protein-design tools are relevant.

Suggested rule:

```text
base system prompt + protein workflow prompt + rendered tool schemas
```

Keep the base prompt generic; keep protein-specific workflow constraints in
the workflow prompt.

### 2. Container Runtime Profiles

Define named runtime profiles:

- `local`: use commands from `PATH` or `PROTEIN_DESIGN_*_CMD`;
- `docker-generation`: use generation image and mounted workspace;
- `docker-validation`: use validation image and mounted workspace;
- `hf-jobs`: dispatch long GPU jobs through Hugging Face Jobs.

Profiles should be config-driven so the frontend and CLI do not need separate
execution logic.

### 3. Artifact Viewer Integration

Expose generated manifests and validation reports through existing backend
session artifacts. Useful first artifacts:

- ACE playbook JSON and rendered Markdown;
- candidate ranking table;
- Chai-1/Protenix comparison table;
- Foldseek cluster TSV;
- final report Markdown.

### 4. Test Fixtures

Add small synthetic PDB fixtures and fake command scripts under tests so the
subprocess wrappers can be tested without GPU dependencies.

Coverage targets:

- command construction;
- stdout/stderr parsing;
- OOM correction status;
- manifest discovery;
- validation metric parsing;
- Foldseek path handling.

## What Not To Optimize Yet

Avoid these until real bottlenecks are measured:

- rewriting the agent loop in another language;
- introducing a separate workflow engine;
- importing heavy GPU libraries into the backend process;
- adding a database schema for candidates before manifests stabilize;
- broad refactors of the generic tool router.

The fastest path is to keep the existing runtime stable and make protein design
tools more structured, observable, and testable.
