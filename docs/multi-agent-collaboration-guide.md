# Multi-Agent Collaboration Guide

Last reviewed: 2026-05-16

## Design Principle

LLM-Harness treats multi-agent behavior as a harness-level lifecycle concern,
not as free-form group chat. AIDD-Intern follows that pattern: roles,
permissions, handoff packages, artifacts, context budgets, and verification
gates should be explicit and auditable.

The first implementation is intentionally lightweight:

- a role registry in `agent/roles/`;
- a structured `role_handoff` tool;
- protein-design specialist roles in
  `agent/domain_packs/protein_design/roles.py`;
- artifact-first handoff rather than replaying full conversation history.

## Role Model

Each role has:

- `name`
- `description`
- `responsibilities`
- `allowed_tools`
- `output_contract`
- `max_context_tokens`
- `can_write`
- `can_run_gpu`
- `requires_verification`

Generic roles:

- `supervisor`: decomposes tasks, delegates, merges outputs, enforces budgets.
- `researcher`: gathers source-backed facts and evidence tables.
- `executor`: runs approved tools and records manifests.
- `verifier`: independently checks candidates and claims.
- `reviewer`: finds bugs, unsupported claims, and missing tests.

Protein-design roles:

- `structural_biologist`: structures, hotspots, glycans, interface physics.
- `protein_designer`: epitope/scaffold choice and generation strategy.
- `orthogonal_validator`: Chai-1/Protenix/Rosetta/Foldseek-style validation.

## Handoff Protocol

Use the `role_handoff` tool before delegating or moving artifacts between
roles. It creates a machine-readable package:

```json
{
  "source_role": "supervisor",
  "target_role": "verifier",
  "task_intent": "Check candidate metrics for reward hacking.",
  "constraints": ["ipTM > 0.8", "pLDDT > 80"],
  "artifacts": ["validation_metrics.json"],
  "evidence": [{"source": "foldseek_clusters.tsv"}],
  "open_questions": ["Do Chai-1 and Protenix agree?"],
  "permissions": {
    "can_write": false,
    "can_run_gpu": false,
    "allowed_tools": ["aidd_bio", "protein_design_ace_playbook"],
    "requires_verification": false
  },
  "budget": {"max_context_tokens": 16000},
  "risk_level": "high"
}
```

The handoff package is deliberately compact so 65K local models can perform
specialist work without receiving the full session history.

## Recommended Collaboration Pattern

Use supervisor + specialists:

```text
Supervisor
  -> Researcher
  -> Structural Biologist
  -> Protein Designer
  -> Executor
  -> Orthogonal Validator
  -> Reviewer
```

Avoid all-agent group chat. It is expensive, hard to audit, and quickly fills
small context windows.

## Context Strategy

Roles should receive:

- the task intent;
- relevant artifacts by path;
- a short evidence table;
- constraints and budget;
- open questions.

Roles should not receive:

- full raw logs unless their task is log analysis;
- entire previous conversation history;
- unrelated artifacts from other branches of work;
- permissions broader than their role needs.

This pairs with `docs/context-management-guide.md`, which defines context
window policies for 65K local models and larger hosted models.

## Verification Gates

High-risk transitions should require independent verification:

- accepting a generated binder candidate;
- expanding GPU sampling;
- concluding that a structure is validated;
- changing core workflow thresholds;
- moving from computational prioritization to wet-lab recommendation.

The verifier should inspect artifacts and metrics, not the designer's
self-justification. This reduces confirmation bias.

## Future Work

Useful next steps:

1. Add a supervisor scheduler that chooses role assignments from task type and
   model context window.
2. Store handoff packages in session traces for failure diagnosis.
3. Attach role labels to events and telemetry.
4. Route small fixed-format tasks to local 65K models and reserve larger models
   for synthesis or high-risk review.
5. Feed verified lessons into ACE playbooks as shared role memory.

