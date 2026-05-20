# AIDD Binder Workflow Guide

Last reviewed: 2026-05-19

## Purpose

The AIDD binder workflow is the narrow first product surface for AIDD-Intern:
de novo binder design for AIDD targets, currently focused on protein binder
campaigns. It follows three design constraints:

- keep the generic agent runtime reusable;
- expose mature biology and design engines through declarative tools;
- make every final binder recommendation traceable to requirements, evidence,
  filters, and residual risks.

The generic runtime remains a durable tool-using harness with persistent session
traces, MCP integration, and clear planning loops. The AIDD-specific layer
should remain opinionated about binder design rather than becoming a general
science-writing agent.

## Default Campaign Loop

The pack expects the agent to run a campaign in this order:

1. Intake the target, biological assembly, chain(s), desired epitope or hotspot,
   no-go regions, binder length, assay, and developability constraints.
2. Use `aidd_bio`, web search, papers, RCSB, UniProt, AlphaFold DB, and
   Foldseek to collect target biology, known structures, homologs, PTMs,
   glycans, membrane context, and existing binders.
3. Call `binder_design(operation="plan_campaign")` to convert the user request
   into difficulty, tool strategy, risk register, acceptance criteria, and open
   questions.
4. Create a project manifest with
   `binder_design(operation="create_project")`; the manifest stores the
   campaign plan next to the generated output folders.
5. Dispatch generation through ProteinMCP or the built-in protein-design tools:
   PXDesign for broad exploration, BoltzGen for constrained sites, and
   BindCraft for iterative refinement.
6. Validate shortlists with an orthogonal predictor such as Chai-1, Protenix,
   or another AlphaFold-style complex predictor.
7. Rank with `binder_design(operation="rank_candidates")`; candidates are
   tagged as `advance`, `hold_for_orthogonal_validation`, or `reject`.
8. Cluster by fold or interface geometry and keep diverse representatives for
   manual structural review and wet-lab handoff.
9. When a workflow becomes stable across campaigns, export it as a reusable
   skill card with `binder_design(operation="export_skill")` so the next run
   can start from a file-backed recipe rather than raw transcript memory.

## Binder Tool Surface

`binder_design` supports:

- `plan_campaign`: returns campaign difficulty, recommended tool sequence,
  risk register, acceptance criteria, and missing intake questions.
- `create_project`: writes `binder_project.json` with target metadata,
  requirements, workflow stages, and the campaign plan.
- `inspect_outputs`: scans generator output directories and reports available
  metric files and normalized metric keys.
- `rank_candidates`: reads compatible CSV metrics, applies filters, computes a
  combined rank score, attaches validation tier and next actions, and returns
  top candidates plus one representative per `fold_cluster`.
- `export_skill`: writes a reusable Markdown skill card under
  `project_dir/skills/` using the manifest as the source of truth. This is the
  Binder-side analogue of Hermes-style skill promotion and Claude Code project
  memory.

The CSV parser accepts common names from BindCraft/PXDesign/BoltzGen-style
outputs, including `plddt`, `iptm`, `ipae`, `pae`, `interface_score`,
`clashes`, `rmsd`, `sequence`, `structure_path`, `validation_source`, and
`fold_cluster`. It also understands interface and developability metrics such
as contacts, hydrogen bonds, buried SASA, hydrophobic SASA, and aggregation
score when present.

## Acceptance Criteria

Default filters are intentionally conservative for early triage:

```json
{
  "plddt": 80,
  "iptm": 0.75,
  "ipae": 8,
  "clashes": 0,
  "rmsd": 3
}
```

Strict planning raises these to `plddt >= 85`, `iptm >= 0.8`, `ipae <= 5`,
`clashes <= 0`, and `rmsd <= 2.5`. These are not wet-lab success guarantees;
they are gates for deciding what deserves additional compute and human review.

## Risk Rules

The default risk register always flags:

- single-model reward hacking;
- false-positive interface confidence.

It adds campaign-specific risks when requirements mention glycosylation, PTMs,
membrane context, species cross-reactivity, or forbidden epitopes. The final
report should explicitly state which risks were resolved by computation and
which remain experimental risks.

## Relationship To Protein Design Tools

Use `binder_design` as the high-level campaign layer. It is lightweight and
works even when heavy GPU tools are unavailable.

Use the protein-design tools when you need direct local specs for PXDesign,
BoltzGen, BindCraft, validation dispatch, GPU preflight, and ACE playbook
memory. Large model weights, PyRosetta, CUDA frameworks, and long-running
scientific jobs should stay behind subprocess, container, MCP, sandbox, or HF
Jobs boundaries.

## Skill Promotion

The skill export is intentionally file-backed. A generated skill card should be
small, readable, and evidence-based:

- keep the manifest as the source of truth;
- record the stable intake questions, tool strategy, filters, and failure modes;
- prune dead steps when a later campaign proves they no longer help;
- promote only workflows that repeat, because that is what makes them useful.

This matches the pattern used by Hermes-style agents and OpenClaw-style
workspace memory: keep durable lessons in Markdown files, then load them again
when a later run repeats the same shape of work.

## Verification

Focused checks:

```bash
uv run pytest tests/unit/test_binder_design_tool.py
uv run pytest tests/unit/test_protein_design_workflow.py
```
