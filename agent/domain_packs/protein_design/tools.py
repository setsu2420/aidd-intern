"""Tool registry for protein binder generation backends."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from agent.domain_packs.protein_design.ace import (
    ACE_PLAYBOOK_TOOL_SPEC,
    ace_playbook_handler,
)


CUDA_OOM_RE = re.compile(
    r"(cuda out of memory|out-of-memory|oom|cublas.*alloc|cudnn.*alloc)",
    re.IGNORECASE,
)
MIN_SAFE_GPU_FREE_MB = 8_000
TOOL_GPU_MB_PER_SAMPLE = {
    "pxdesign": 450,
    "boltzgen": 700,
}
TOOL_BASE_GPU_MB = {
    "pxdesign": 6_000,
    "boltzgen": 10_000,
    "bindcraft": 14_000,
}
MAX_TOOL_OUTPUT_CHARS = 12_000


def _safe_path(raw: str, *, must_exist: bool = True) -> Path:
    path = Path(raw).expanduser().resolve()
    if must_exist and not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    return path


def _parse_hardware_errors(output: str) -> dict[str, Any]:
    return {
        "cuda_oom": bool(CUDA_OOM_RE.search(output)),
        "suggested_correction": (
            "Reduce num_samples or batch size and enable mixed precision."
            if CUDA_OOM_RE.search(output)
            else None
        ),
    }


def _detect_gpu_free_mb() -> list[int]:
    """Return free memory for visible GPUs in MiB, best effort."""
    override = os.environ.get("PROTEIN_DESIGN_GPU_FREE_MB")
    if override:
        return [int(value.strip()) for value in override.split(",") if value.strip()]
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except Exception:
        return []
    free_mb: list[int] = []
    for line in result.stdout.splitlines():
        try:
            free_mb.append(int(line.strip()))
        except ValueError:
            continue
    return free_mb


def _gpu_plan(
    tool: str,
    *,
    num_samples: int | None = None,
    binder_length: int | None = None,
    iterations: int | None = None,
) -> dict[str, Any]:
    """Create a conservative GPU execution plan from current free VRAM."""
    free_mb = _detect_gpu_free_mb()
    best_free = max(free_mb) if free_mb else None
    best_index = free_mb.index(best_free) if best_free is not None else None
    plan: dict[str, Any] = {
        "gpu_free_mb": free_mb,
        "selected_gpu_free_mb": best_free,
        "selected_gpu_index": best_index,
        "adjusted": False,
        "can_run": True,
        "reason": None,
    }
    if best_free is None:
        plan["reason"] = (
            "GPU free memory unavailable; proceeding with conservative defaults."
        )
        return plan
    if best_free < MIN_SAFE_GPU_FREE_MB:
        plan.update(
            {
                "can_run": False,
                "reason": (
                    f"Insufficient free GPU memory: {best_free} MiB available, "
                    f"minimum safe threshold is {MIN_SAFE_GPU_FREE_MB} MiB."
                ),
            }
        )
        return plan

    base = TOOL_BASE_GPU_MB.get(tool, MIN_SAFE_GPU_FREE_MB)
    available = max(0, best_free - base)
    if num_samples is not None and tool in TOOL_GPU_MB_PER_SAMPLE:
        per_sample = TOOL_GPU_MB_PER_SAMPLE[tool]
        max_samples = max(1, available // per_sample)
        if num_samples > max_samples:
            plan.update(
                {
                    "adjusted": True,
                    "original_num_samples": num_samples,
                    "num_samples": int(max_samples),
                    "reason": (
                        f"Downscaled {tool} num_samples from {num_samples} to "
                        f"{max_samples} based on {best_free} MiB free GPU memory."
                    ),
                }
            )
        else:
            plan["num_samples"] = num_samples

    if tool == "bindcraft":
        length = int(binder_length or 100)
        iters = int(iterations or 50)
        estimated = base + max(0, length - 80) * 80 + max(0, iters - 25) * 120
        if estimated > best_free:
            max_iters = max(
                1, int((best_free - base - max(0, length - 80) * 80) // 120 + 25)
            )
            if max_iters < iters:
                plan.update(
                    {
                        "adjusted": True,
                        "original_iterations": iters,
                        "iterations": max_iters,
                        "reason": (
                            f"Downscaled BindCraft iterations from {iters} to "
                            f"{max_iters} based on {best_free} MiB free GPU memory."
                        ),
                    }
                )
            if max_iters < 1:
                plan.update(
                    {
                        "can_run": False,
                        "reason": (
                            f"Insufficient free GPU memory for binder_length={length}: "
                            f"{best_free} MiB available."
                        ),
                    }
                )
        else:
            plan["iterations"] = iters
    return plan


def _json_arg(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("constraints_json must be valid JSON") from exc


def _base_output(
    tool: str,
    command: list[str],
    returncode: int,
    stdout: str,
    stderr: str,
    gpu_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    combined = "\n".join(part for part in [stdout, stderr] if part)
    hardware = _parse_hardware_errors(combined)
    stdout_truncated = len(stdout) > MAX_TOOL_OUTPUT_CHARS
    stderr_truncated = len(stderr) > MAX_TOOL_OUTPUT_CHARS
    return {
        "tool": tool,
        "command": command,
        "returncode": returncode,
        "stdout": stdout[-MAX_TOOL_OUTPUT_CHARS:] if stdout_truncated else stdout,
        "stderr": stderr[-MAX_TOOL_OUTPUT_CHARS:] if stderr_truncated else stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "gpu_plan": gpu_plan or {},
        "hardware_errors": hardware,
        "status": "needs_runtime_correction"
        if hardware["cuda_oom"]
        else ("completed" if returncode == 0 else "failed"),
    }


async def _run_command(
    command: list[str],
    timeout_s: int | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
    except FileNotFoundError as exc:
        missing = command[0] if command else "<empty command>"
        return (
            127,
            "",
            f"Executable not found: {missing}. Configure the runtime command or ProteinMCP launcher. ({exc})",
        )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout_s
        )
    except TimeoutError:
        process.kill()
        stdout_bytes, stderr_bytes = await process.communicate()
        return (
            124,
            stdout_bytes.decode(errors="replace"),
            stderr_bytes.decode(errors="replace") + "\nTimed out.",
        )
    return (
        process.returncode or 0,
        stdout_bytes.decode(errors="replace"),
        stderr_bytes.decode(errors="replace"),
    )


def _runtime_prefix(tool_name: str, tool_runtime: str) -> list[str]:
    env_name = f"PROTEIN_DESIGN_{tool_name.upper()}_CMD"
    configured = os.environ.get(env_name)
    if configured:
        return shlex.split(configured)

    if tool_runtime == "sandbox":
        image = os.environ.get(
            f"PROTEIN_DESIGN_{tool_name.upper()}_IMAGE",
            f"aidd-intern/protein-design-{tool_name}:latest",
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
            tool_name,
        ]
    return [tool_name]


def _bindcraft_mcp_root() -> Path:
    return Path(
        os.environ.get(
            "AIDD_INTERN_BINDCRAFT_MCP_DIR",
            str(
                Path.home() / ".cache" / "aidd-intern" / "proteinmcp" / "bindcraft_mcp"
            ),
        )
    ).expanduser()


def _bindcraft_default_paths() -> dict[str, Path]:
    root = _bindcraft_mcp_root()
    return {
        "root": root,
        "python": Path(
            os.environ.get(
                "AIDD_INTERN_BINDCRAFT_MCP_PYTHON", str(root / "env/bin/python")
            )
        ).expanduser(),
        "script": root / "scripts/run_bindcraft.py",
        "scripts_dir": root / "scripts",
        "filters": root / "repo/BindCraft/settings_filters/default_filters.json",
        "advanced": root
        / "repo/BindCraft/settings_advanced/default_4stage_multimer.json",
        "params": root / "repo/scripts/params",
    }


def _write_bindcraft_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


async def run_pxdesign_handler(
    target_pdb: str,
    interface_residues: str,
    num_samples: int,
    tool_runtime: str = "local",
) -> dict[str, Any]:
    """Execute PXdesign diffusion and sequence design through an isolated CLI."""
    target = _safe_path(target_pdb)
    gpu_plan = _gpu_plan("pxdesign", num_samples=num_samples)
    if not gpu_plan["can_run"]:
        return _base_output("pxdesign", [], 75, "", gpu_plan["reason"] or "", gpu_plan)
    num_samples = int(gpu_plan.get("num_samples", num_samples))
    command = [
        *_runtime_prefix("pxdesign", tool_runtime),
        "generate",
        "--target-pdb",
        str(target),
        "--interface-residues",
        interface_residues,
        "--num-samples",
        str(num_samples),
        "--mixed-precision",
    ]
    returncode, stdout, stderr = await _run_command(command)
    return _base_output("pxdesign", command, returncode, stdout, stderr, gpu_plan)


async def run_boltzgen_handler(
    target_pdb: str,
    constraints_json: str,
    num_samples: int = 100,
    tool_runtime: str = "local",
) -> dict[str, Any]:
    """Invoke BoltzGen for constraint-conditioned binder generation."""
    target = _safe_path(target_pdb)
    gpu_plan = _gpu_plan("boltzgen", num_samples=num_samples)
    if not gpu_plan["can_run"]:
        return _base_output("boltzgen", [], 75, "", gpu_plan["reason"] or "", gpu_plan)
    num_samples = int(gpu_plan.get("num_samples", num_samples))
    constraints = _json_arg(constraints_json)
    constraints_file = target.parent / "boltzgen_constraints.json"
    constraints_file.write_text(
        json.dumps(constraints, indent=2) + "\n", encoding="utf-8"
    )
    command = [
        *_runtime_prefix("boltzgen", tool_runtime),
        "generate",
        "--target-pdb",
        str(target),
        "--constraints",
        str(constraints_file),
        "--num-samples",
        str(num_samples),
    ]
    returncode, stdout, stderr = await _run_command(command)
    return _base_output("boltzgen", command, returncode, stdout, stderr, gpu_plan)


async def run_bindcraft_handler(
    target_pdb: str,
    binder_length: int,
    iterations: int = 50,
    tool_runtime: str = "local",
    output_dir: str | None = None,
    binder_name: str | None = None,
    target_chains: str = "A",
    hotspot_residues: str | None = None,
    num_designs: int = 1,
    max_trajectories: int | None = None,
    device: int | None = None,
    timeout_s: int | None = None,
) -> dict[str, Any]:
    """Run BindCraft iterative optimization."""
    target = _safe_path(target_pdb)
    gpu_plan = _gpu_plan(
        "bindcraft", binder_length=binder_length, iterations=iterations
    )
    if not gpu_plan["can_run"]:
        return _base_output("bindcraft", [], 75, "", gpu_plan["reason"] or "", gpu_plan)
    paths = _bindcraft_default_paths()
    out_dir = _safe_path(
        output_dir or str(target.parent / f"{target.stem}_bindcraft_out"),
        must_exist=False,
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    if tool_runtime == "local":
        missing = [
            str(path)
            for path in [
                paths["python"],
                paths["script"],
                paths["filters"],
                paths["advanced"],
                paths["params"],
            ]
            if not path.exists()
        ]
        if missing:
            return _base_output(
                "bindcraft",
                [],
                127,
                "",
                "Missing BindCraft runtime files: " + ", ".join(missing),
                gpu_plan,
            )

        target_settings = {
            "design_path": str(out_dir),
            "binder_name": binder_name or target.stem,
            "starting_pdb": str(target),
            "chains": target_chains,
            "target_hotspot_residues": hotspot_residues or "",
            "lengths": [int(binder_length), int(binder_length)],
            "number_of_final_designs": int(num_designs),
        }
        settings_path = _write_bindcraft_json(
            out_dir / "target_settings.json", target_settings
        )

        advanced = json.loads(paths["advanced"].read_text(encoding="utf-8"))
        advanced["af_params_dir"] = str(paths["params"])
        # The local ProteinMCP/BindCraft runtime does not always ship ffmpeg.
        # Animations are nonessential and can otherwise abort low-confidence runs.
        advanced["save_design_animations"] = False
        advanced["zip_animations"] = False
        if max_trajectories is not None:
            advanced["max_trajectories"] = max(1, int(max_trajectories))
        if "num_recycles_design" in advanced and iterations:
            advanced["num_recycles_design"] = max(
                1, min(int(iterations), int(advanced["num_recycles_design"]))
            )
        advanced_path = _write_bindcraft_json(
            out_dir / "aidd_advanced_settings.json", advanced
        )

        command = [
            str(paths["python"]),
            str(paths["script"]),
            f"--settings={settings_path}",
            f"--filters={paths['filters']}",
            f"--advanced={advanced_path}",
        ]
        env = os.environ.copy()
        selected_device = device
        if selected_device is None:
            selected_device = int(gpu_plan.get("selected_gpu_index") or 0)
        env["CUDA_VISIBLE_DEVICES"] = str(selected_device)
        env["XLA_FLAGS"] = "--xla_gpu_enable_triton_gemm=false"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = str(paths["scripts_dir"]) + (
            f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
        )
        returncode, stdout, stderr = await _run_command(
            command,
            timeout_s=timeout_s,
            cwd=str(paths["scripts_dir"]),
            env=env,
        )
    else:
        command = [
            *_runtime_prefix("bindcraft", tool_runtime),
            "run",
            "--target-pdb",
            str(target),
            "--binder-length",
            str(binder_length),
            "--iterations",
            str(iterations),
        ]
        returncode, stdout, stderr = await _run_command(command, timeout_s=timeout_s)

    result = _base_output("bindcraft", command, returncode, stdout, stderr, gpu_plan)
    result["output_dir"] = str(out_dir)
    result["metric_files"] = [str(path) for path in sorted(out_dir.glob("*.csv"))]
    return result


def _format_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


async def _pxdesign_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    result = await run_pxdesign_handler(
        target_pdb=arguments["target_pdb"],
        interface_residues=arguments["interface_residues"],
        num_samples=int(arguments.get("num_samples") or 100),
        tool_runtime=arguments.get("tool_runtime") or "local",
    )
    return _format_result(result), result["returncode"] == 0


async def _boltzgen_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    result = await run_boltzgen_handler(
        target_pdb=arguments["target_pdb"],
        constraints_json=arguments["constraints_json"],
        num_samples=int(arguments.get("num_samples") or 100),
        tool_runtime=arguments.get("tool_runtime") or "local",
    )
    return _format_result(result), result["returncode"] == 0


async def _bindcraft_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    result = await run_bindcraft_handler(
        target_pdb=arguments["target_pdb"],
        binder_length=int(arguments["binder_length"]),
        iterations=int(arguments.get("iterations") or 50),
        tool_runtime=arguments.get("tool_runtime") or "local",
        output_dir=arguments.get("output_dir"),
        binder_name=arguments.get("binder_name"),
        target_chains=arguments.get("target_chains") or "A",
        hotspot_residues=arguments.get("hotspot_residues"),
        num_designs=int(arguments.get("num_designs") or 1),
        max_trajectories=(
            int(arguments["max_trajectories"])
            if arguments.get("max_trajectories") is not None
            else None
        ),
        device=arguments.get("device"),
        timeout_s=arguments.get("timeout_s"),
    )
    return _format_result(result), result["returncode"] == 0


def create_protein_design_tools(tool_spec_cls: type | None = None) -> list[Any]:
    """Create ToolSpec instances for the protein-design domain pack."""
    if tool_spec_cls is None:
        from agent.core.tools import ToolSpec

        tool_spec_cls = ToolSpec
    return [
        tool_spec_cls(
            name=ACE_PLAYBOOK_TOOL_SPEC["name"],
            description=ACE_PLAYBOOK_TOOL_SPEC["description"],
            parameters=ACE_PLAYBOOK_TOOL_SPEC["parameters"],
            handler=ace_playbook_handler,
        ),
        tool_spec_cls(
            name="run_pxdesign",
            description=(
                "Generate protein binders using PXdesign DiT backbone diffusion "
                "and ProteinMPNN sequence design."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "target_pdb": {
                        "type": "string",
                        "description": "Path to target PDB file.",
                    },
                    "interface_residues": {
                        "type": "string",
                        "description": "Comma-separated target interface residue indices.",
                    },
                    "num_samples": {"type": "integer", "default": 100},
                    "tool_runtime": {
                        "type": "string",
                        "enum": ["local", "sandbox"],
                        "default": "local",
                    },
                },
                "required": ["target_pdb", "interface_residues"],
            },
            handler=_pxdesign_tool,
        ),
        tool_spec_cls(
            name="run_boltzgen",
            description="Generate binders under topological constraints using BoltzGen.",
            parameters={
                "type": "object",
                "properties": {
                    "target_pdb": {"type": "string"},
                    "constraints_json": {
                        "type": "string",
                        "description": "JSON serialized geometric constraints.",
                    },
                    "num_samples": {"type": "integer", "default": 100},
                    "tool_runtime": {
                        "type": "string",
                        "enum": ["local", "sandbox"],
                        "default": "local",
                    },
                },
                "required": ["target_pdb", "constraints_json"],
            },
            handler=_boltzgen_tool,
        ),
        tool_spec_cls(
            name="run_bindcraft",
            description="Run multi-round automated binder optimization via BindCraft.",
            parameters={
                "type": "object",
                "properties": {
                    "target_pdb": {"type": "string"},
                    "binder_length": {
                        "type": "integer",
                        "description": "Target binder length in amino acids.",
                    },
                    "iterations": {"type": "integer", "default": 50},
                    "output_dir": {
                        "type": "string",
                        "description": "Directory for BindCraft outputs.",
                    },
                    "binder_name": {
                        "type": "string",
                        "description": "Prefix for generated binder designs.",
                    },
                    "target_chains": {
                        "type": "string",
                        "default": "A",
                        "description": "Target chain IDs for interface design.",
                    },
                    "hotspot_residues": {
                        "type": "string",
                        "description": "Comma-separated target hotspot residue numbers.",
                    },
                    "num_designs": {
                        "type": "integer",
                        "default": 1,
                        "description": "Number of final accepted designs to request.",
                    },
                    "max_trajectories": {
                        "type": "integer",
                        "description": "Optional cap on attempted BindCraft trajectories.",
                    },
                    "device": {
                        "type": "integer",
                        "description": "GPU index to use. Defaults to the GPU with most free memory.",
                    },
                    "timeout_s": {
                        "type": "integer",
                        "description": "Optional command timeout in seconds.",
                    },
                    "tool_runtime": {
                        "type": "string",
                        "enum": ["local", "sandbox"],
                        "default": "local",
                    },
                },
                "required": ["target_pdb", "binder_length"],
            },
            handler=_bindcraft_tool,
        ),
    ]
