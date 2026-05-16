"""Binder design workflow utilities.

This tool is intentionally small and local. It gives the agent a stable
workflow surface for binder-design projects independent of which generator
produced the files (BindCraft, BoltzGen, PXDesign, or a later MCP).
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


METRIC_ALIASES = {
    "name": [
        "name",
        "design",
        "design_name",
        "binder",
        "binder_name",
        "model",
        "description",
    ],
    "plddt": ["plddt", "average_plddt", "avg_plddt", "mean_plddt"],
    "iptm": ["iptm", "ipTM", "interface_ptm"],
    "ipae": ["ipae", "average_i_pae", "average_ipae", "i_pae", "pae_interaction"],
    "pae": ["pae", "average_pae", "mean_pae"],
    "interface_score": [
        "interface_score",
        "interface_energy",
        "interface_delta_g",
        "interface_dg",
        "interface_sc",
    ],
    "binder_score": ["binder_score", "score", "quality_score", "confidence_score"],
    "clashes": ["clashes", "num_clashes", "clash_count"],
    "rmsd": ["rmsd", "backbone_rmsd", "bb_rmsd"],
    "sequence": ["sequence", "binder_sequence", "seq"],
    "structure_path": ["structure_path", "pdb", "pdb_path", "cif", "cif_path"],
}

HIGH_IS_BETTER = {"plddt", "iptm", "binder_score"}
LOW_IS_BETTER = {"ipae", "pae", "interface_score", "clashes", "rmsd"}


def _safe_path(raw: str | None) -> Path:
    if not raw:
        raise ValueError("path is required")
    return Path(raw).expanduser().resolve()


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_value(row: dict[str, Any], aliases: list[str]) -> Any:
    lower_map = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in aliases:
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    return None


def _normalize_row(
    row: dict[str, Any], source_file: Path, index: int
) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "source_file": str(source_file),
        "source_row": index,
    }
    for metric, aliases in METRIC_ALIASES.items():
        value = _find_value(row, aliases)
        if metric in HIGH_IS_BETTER or metric in LOW_IS_BETTER:
            normalized[metric] = _as_float(value)
        elif value not in (None, ""):
            normalized[metric] = str(value)

    if "name" not in normalized:
        normalized["name"] = f"{source_file.stem}:{index}"
    return normalized


def _discover_metric_files(root: Path) -> list[Path]:
    patterns = [
        "*final*design*stats*.csv",
        "*design*stats*.csv",
        "*metrics*.csv",
        "*scores*.csv",
        "*.csv",
    ]
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                files.append(path)
    return files


def _read_candidates(
    root: Path, metric_files: list[str] | None = None
) -> list[dict[str, Any]]:
    files = (
        [_safe_path(path) for path in metric_files]
        if metric_files
        else _discover_metric_files(root)
    )
    candidates: list[dict[str, Any]] = []
    for file_path in files:
        if not file_path.exists() or file_path.suffix.lower() != ".csv":
            continue
        with file_path.open(
            "r", encoding="utf-8", errors="replace", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                candidates.append(_normalize_row(row, file_path, index))
    return candidates


def _score_candidate(candidate: dict[str, Any]) -> float:
    score = 0.0
    plddt = candidate.get("plddt")
    if plddt is not None:
        score += plddt / 100.0
    iptm = candidate.get("iptm")
    if iptm is not None:
        score += iptm
    binder_score = candidate.get("binder_score")
    if binder_score is not None:
        score += binder_score / 10.0

    ipae = candidate.get("ipae")
    if ipae is not None:
        score -= ipae / 10.0
    pae = candidate.get("pae")
    if pae is not None:
        score -= pae / 20.0
    rmsd = candidate.get("rmsd")
    if rmsd is not None:
        score -= rmsd / 5.0
    clashes = candidate.get("clashes")
    if clashes is not None:
        score -= clashes / 10.0
    interface_score = candidate.get("interface_score")
    if interface_score is not None:
        # Negative interface energies are favorable.
        score += -interface_score / 50.0
    return round(score, 4)


def _passes_filters(
    candidate: dict[str, Any], filters: dict[str, Any]
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for key, threshold in filters.items():
        value = candidate.get(key)
        numeric_threshold = _as_float(threshold)
        if numeric_threshold is None or value is None:
            continue
        if key in HIGH_IS_BETTER and value < numeric_threshold:
            failures.append(f"{key}={value} < {numeric_threshold}")
        elif key in LOW_IS_BETTER and value > numeric_threshold:
            failures.append(f"{key}={value} > {numeric_threshold}")
    return not failures, failures


def _format_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


BINDER_DESIGN_TOOL_SPEC = {
    "name": "binder_design",
    "description": (
        "Manage AIDD binder-design projects and rank generated binder candidates. "
        "Use after literature/target validation and after BindCraft, BoltzGen, "
        "PXDesign, or another generator has produced outputs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["create_project", "inspect_outputs", "rank_candidates"],
                "description": "Binder-design workflow operation to run.",
            },
            "project_dir": {
                "type": "string",
                "description": "Project directory for manifests and outputs.",
            },
            "target_name": {
                "type": "string",
                "description": "Target protein name or identifier for create_project.",
            },
            "target_structure": {
                "type": "string",
                "description": "PDB/mmCIF path, PDB ID, AlphaFold accession, or URL.",
            },
            "requirements": {
                "type": "object",
                "description": "User constraints such as chains, epitope, length, and exclusions.",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Generator/evaluator tools planned for the project.",
            },
            "outputs_dir": {
                "type": "string",
                "description": "Directory containing generator outputs to inspect or rank.",
            },
            "metric_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional explicit CSV metric files to parse.",
            },
            "filters": {
                "type": "object",
                "description": (
                    "Numeric filter thresholds. High-is-better: plddt, iptm, binder_score. "
                    "Low-is-better: ipae, pae, interface_score, clashes, rmsd."
                ),
            },
            "top_k": {
                "type": "integer",
                "description": "Number of ranked candidates to return.",
                "default": 10,
            },
        },
        "required": ["operation"],
    },
}


async def binder_design_handler(arguments: dict[str, Any]) -> tuple[str, bool]:
    try:
        operation = arguments.get("operation")
        if operation == "create_project":
            project_dir = _safe_path(arguments.get("project_dir"))
            project_dir.mkdir(parents=True, exist_ok=True)
            manifest = {
                "created_at": datetime.now(UTC).isoformat(),
                "target_name": arguments.get("target_name"),
                "target_structure": arguments.get("target_structure"),
                "requirements": arguments.get("requirements") or {},
                "tools": arguments.get("tools")
                or ["aidd_bio", "bindcraft", "boltzgen", "pxdesign"],
                "workflow": [
                    "validate target and biological records",
                    "research target biology and known binders",
                    "generate designs",
                    "compute/collect structure and interface metrics",
                    "rank and filter candidates",
                    "write final binder report",
                ],
            }
            manifest_path = project_dir / "binder_project.json"
            manifest_path.write_text(_format_result(manifest) + "\n", encoding="utf-8")
            (project_dir / "outputs").mkdir(exist_ok=True)
            return _format_result(
                {"status": "created", "manifest": str(manifest_path)}
            ), True

        if operation == "inspect_outputs":
            root = _safe_path(
                arguments.get("outputs_dir") or arguments.get("project_dir")
            )
            candidates = _read_candidates(root, arguments.get("metric_files"))
            metric_files = sorted(
                {candidate["source_file"] for candidate in candidates}
            )
            return (
                _format_result(
                    {
                        "status": "inspected",
                        "outputs_dir": str(root),
                        "metric_files": metric_files,
                        "candidate_count": len(candidates),
                        "available_metrics": sorted(
                            {
                                key
                                for candidate in candidates
                                for key, value in candidate.items()
                                if value is not None
                            }
                        ),
                    }
                ),
                True,
            )

        if operation == "rank_candidates":
            root = _safe_path(
                arguments.get("outputs_dir") or arguments.get("project_dir")
            )
            top_k = int(arguments.get("top_k") or 10)
            filters = arguments.get("filters") or {}
            candidates = _read_candidates(root, arguments.get("metric_files"))
            ranked = []
            rejected = []
            for candidate in candidates:
                passed, failures = _passes_filters(candidate, filters)
                candidate = dict(candidate)
                candidate["rank_score"] = _score_candidate(candidate)
                if passed:
                    ranked.append(candidate)
                else:
                    candidate["filter_failures"] = failures
                    rejected.append(candidate)
            ranked.sort(key=lambda item: item["rank_score"], reverse=True)
            return (
                _format_result(
                    {
                        "status": "ranked",
                        "outputs_dir": str(root),
                        "candidate_count": len(candidates),
                        "passed_count": len(ranked),
                        "rejected_count": len(rejected),
                        "top_candidates": ranked[:top_k],
                    }
                ),
                True,
            )

        return (
            _format_result(
                {
                    "status": "error",
                    "message": "Unknown or missing operation. Use create_project, inspect_outputs, or rank_candidates.",
                }
            ),
            False,
        )
    except Exception as exc:
        return _format_result({"status": "error", "message": str(exc)}), False
