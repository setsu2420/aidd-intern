"""Orthogonal validation helpers for protein binder candidates."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from pathlib import Path
from typing import Any


def _safe_path(raw: str, *, must_exist: bool = True) -> Path:
    path = Path(raw).expanduser().resolve()
    if must_exist and not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    return path


async def _run_command(command: list[str]) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    return (
        process.returncode or 0,
        stdout_bytes.decode(errors="replace"),
        stderr_bytes.decode(errors="replace"),
    )


def _runtime_prefix(name: str) -> list[str]:
    configured = os.environ.get(f"PROTEIN_DESIGN_{name.upper()}_CMD")
    if configured:
        return shlex.split(configured)
    image = os.environ.get(
        f"PROTEIN_DESIGN_{name.upper()}_IMAGE",
        f"aidd-intern/protein-design-{name}:latest",
    )
    return [
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "-v",
        f"{Path.cwd()}:/workspace",
        "-w",
        "/workspace",
        image,
        name,
    ]


def _parse_metrics(stdout: str, metrics_file: Path | None = None) -> dict[str, float]:
    payload: dict[str, Any] = {}
    if metrics_file and metrics_file.exists():
        payload = json.loads(metrics_file.read_text(encoding="utf-8"))
    elif stdout.strip():
        payload = json.loads(stdout)
    return {
        "iptm": float(payload.get("iptm", payload.get("ipTM", 0.0))),
        "plddt": float(payload.get("plddt", payload.get("pLDDT", 0.0))),
        "pae": float(payload.get("pae", payload.get("pAE", 0.0))),
    }


async def evaluate_with_chai1(complex_pdb: str) -> dict[str, float]:
    """Run Chai-1 and extract ipTM, pLDDT, and pAE metrics."""
    complex_path = _safe_path(complex_pdb)
    metrics_file = complex_path.with_suffix(".chai1.metrics.json")
    command = [
        *_runtime_prefix("chai1"),
        "predict",
        "--input",
        str(complex_path),
        "--metrics-json",
        str(metrics_file),
    ]
    returncode, stdout, stderr = await _run_command(command)
    if returncode != 0:
        raise RuntimeError(f"Chai-1 validation failed: {stderr or stdout}")
    return _parse_metrics(stdout, metrics_file)


async def evaluate_with_protenix(complex_pdb: str) -> dict[str, float]:
    """Run Protenix as an orthogonal validator against Chai-1."""
    complex_path = _safe_path(complex_pdb)
    metrics_file = complex_path.with_suffix(".protenix.metrics.json")
    command = [
        *_runtime_prefix("protenix"),
        "predict",
        "--input",
        str(complex_path),
        "--metrics-json",
        str(metrics_file),
    ]
    returncode, stdout, stderr = await _run_command(command)
    if returncode != 0:
        raise RuntimeError(f"Protenix validation failed: {stderr or stdout}")
    return _parse_metrics(stdout, metrics_file)


async def cluster_candidates_foldseek(directory_path: str) -> str:
    """Cluster high-scoring binders with Foldseek and return the cluster TSV path."""
    directory = _safe_path(directory_path)
    output_prefix = directory / "foldseek_clusters"
    command = [
        *_runtime_prefix("foldseek"),
        "easy-cluster",
        str(directory),
        str(output_prefix),
        str(directory / "foldseek_tmp"),
    ]
    returncode, stdout, stderr = await _run_command(command)
    if returncode != 0:
        raise RuntimeError(f"Foldseek clustering failed: {stderr or stdout}")
    return str(output_prefix.parent / f"{output_prefix.name}_cluster.tsv")
