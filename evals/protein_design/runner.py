"""Headless evaluation harness for protein-design workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvaluationTask:
    task_id: str
    target_name: str
    target_pdb_path: str
    known_hotspots: str
    requirements: dict[str, Any] | None = None


HARNESS_LAYERS = {
    "E": "environment",
    "T": "tools",
    "C": "control",
    "L": "learning",
    "O": "observability",
    "V": "validation",
    "G": "governance",
}


def load_tasks(path: str | Path) -> list[EvaluationTask]:
    tasks: list[EvaluationTask] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                tasks.append(EvaluationTask(**json.loads(line)))
    return tasks


def _harness_profile(task: EvaluationTask, target_exists: bool) -> dict[str, Any]:
    """Return ETCLOVG-style harness evidence for one benchmark task."""
    return {
        "schema": "ETCLOVG",
        "layers": {
            "environment": {
                "ready": target_exists,
                "evidence": {
                    "target_pdb_path": task.target_pdb_path,
                    "target_available": target_exists,
                },
            },
            "tools": {
                "ready": True,
                "evidence": {
                    "required_tools": [
                        "aidd_bio",
                        "binder_design",
                        "ProteinMCP generation",
                        "orthogonal validator",
                        "Foldseek/TM-align clustering",
                    ]
                },
            },
            "control": {
                "ready": bool(task.known_hotspots),
                "evidence": {
                    "known_hotspots": task.known_hotspots,
                    "expected_flow": [
                        "plan_campaign",
                        "create_project",
                        "generate",
                        "validate",
                        "rank_candidates",
                        "reflect_run",
                    ],
                },
            },
            "learning": {
                "ready": True,
                "evidence": {
                    "ace_feedback": "run outputs should be converted into ACE delta items"
                },
            },
            "observability": {
                "ready": True,
                "evidence": {
                    "trace_fields": [
                        "task_id",
                        "model_name",
                        "workflow",
                        "target_available",
                        "status",
                    ]
                },
            },
            "validation": {
                "ready": target_exists,
                "evidence": {
                    "success_filters": {
                        "iptm": ">= 0.8",
                        "plddt": ">= 80",
                        "fold_diversity": ">= 1 cluster",
                    }
                },
            },
            "governance": {
                "ready": True,
                "evidence": {
                    "requires_approval_for": [
                        "large GPU sampling",
                        "long BindCraft iterations",
                        "external deploy/publish actions",
                    ]
                },
            },
        },
    }


def _harness_ready(profile: dict[str, Any]) -> bool:
    layers = profile["layers"].values()
    return all(bool(layer["ready"]) for layer in layers)


def _feedback_delta_items(
    task: EvaluationTask, profile: dict[str, Any]
) -> list[dict[str, Any]]:
    failures = [
        name
        for name, layer in profile["layers"].items()
        if not bool(layer.get("ready"))
    ]
    if not failures:
        content = (
            f"Benchmark task {task.task_id} is ready across ETCLOVG layers; "
            "run generation, validation, ranking, and ACE reflection as one traceable loop."
        )
        feedback = "helpful"
    else:
        content = (
            f"Benchmark task {task.task_id} is blocked in harness layers: "
            f"{', '.join(failures)}. Resolve these before spending GPU budget."
        )
        feedback = "neutral"
    return [
        {
            "section": "harness_feedback",
            "content": content,
            "feedback": feedback,
            "source": "protein_design_eval_runner",
            "evidence": {
                "task_id": task.task_id,
                "blocked_layers": failures,
            },
        }
    ]


async def run_evaluation_suite(
    tasks: list[EvaluationTask], model_name: str
) -> list[dict[str, Any]]:
    """Run headless benchmark tasks with the protein_design pack enabled."""
    results: list[dict[str, Any]] = []
    for task in tasks:
        target_exists = Path(task.target_pdb_path).expanduser().exists()
        harness_profile = _harness_profile(task, target_exists)
        harness_ready = _harness_ready(harness_profile)
        results.append(
            {
                "task": asdict(task),
                "model_name": model_name,
                "workflow": "protein_design",
                "target_available": target_exists,
                "status": "skipped_missing_target"
                if not harness_ready
                else "ready_for_headless_agent",
                "harness_ready": harness_ready,
                "harness_profile": harness_profile,
                "feedback_delta_items": _feedback_delta_items(task, harness_profile),
                "success_rate": None,
                "fold_diversity": None,
                "compute_costs": None,
            }
        )
    return results


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="evals/protein_design/tasks.jsonl")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", default="evals/protein_design/results.json")
    args = parser.parse_args()

    results = await run_evaluation_suite(load_tasks(args.tasks), args.model)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(_main())
