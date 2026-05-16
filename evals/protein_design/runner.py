"""Headless evaluation harness for the protein-design domain pack."""

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


def load_tasks(path: str | Path) -> list[EvaluationTask]:
    tasks: list[EvaluationTask] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                tasks.append(EvaluationTask(**json.loads(line)))
    return tasks


async def run_evaluation_suite(
    tasks: list[EvaluationTask], model_name: str
) -> list[dict[str, Any]]:
    """Run headless benchmark tasks with the protein_design pack enabled."""
    results: list[dict[str, Any]] = []
    for task in tasks:
        target_exists = Path(task.target_pdb_path).expanduser().exists()
        results.append(
            {
                "task": asdict(task),
                "model_name": model_name,
                "domain_pack": "protein_design",
                "target_available": target_exists,
                "status": "skipped_missing_target"
                if not target_exists
                else "ready_for_headless_agent",
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
