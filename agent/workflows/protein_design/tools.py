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

from agent.workflows.protein_design.ace import (
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
    "rfd3": 200,
}
TOOL_BASE_GPU_MB = {
    "pxdesign": 6_000,
    "boltzgen": 10_000,
    "bindcraft": 14_000,
    "rfd3": 8_000,
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
    force_run = os.environ.get("AIDD_INTERN_FORCE_GPU_RUN", "").lower() in ("1", "true")
    cpu_fallback = os.environ.get("AIDD_INTERN_CPU_FALLBACK", "").lower() in (
        "1",
        "true",
    )

    if best_free is None:
        if cpu_fallback:
            plan.update(
                {
                    "reason": "GPU free memory unavailable; falling back to CPU mode.",
                    "cpu_fallback": True,
                }
            )
        else:
            plan["reason"] = (
                "GPU free memory unavailable; proceeding with conservative defaults."
            )
        return plan

    if best_free < MIN_SAFE_GPU_FREE_MB:
        if force_run:
            plan.update(
                {
                    "can_run": True,
                    "reason": (
                        f"WARNING: Insufficient free GPU memory ({best_free} MiB < {MIN_SAFE_GPU_FREE_MB} MiB). "
                        "Force-run enabled; proceeding at risk of potential CUDA OOM."
                    ),
                }
            )
        elif cpu_fallback:
            plan.update(
                {
                    "can_run": True,
                    "reason": (
                        f"Insufficient free GPU memory ({best_free} MiB < {MIN_SAFE_GPU_FREE_MB} MiB). "
                        "CPU-fallback enabled; executing on CPU backend."
                    ),
                    "cpu_fallback": True,
                }
            )
        else:
            plan.update(
                {
                    "can_run": False,
                    "reason": (
                        f"Insufficient free GPU memory: {best_free} MiB available, "
                        f"minimum safe threshold is {MIN_SAFE_GPU_FREE_MB} MiB. "
                        "To force run, set AIDD_INTERN_FORCE_GPU_RUN=1. To run on CPU, set AIDD_INTERN_CPU_FALLBACK=1."
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
        engine = os.environ.get("PROTEIN_DESIGN_CONTAINER_ENGINE")
        if not engine:
            import shutil

            if shutil.which("apptainer"):
                engine = "apptainer"
            elif shutil.which("singularity"):
                engine = "singularity"
            else:
                engine = "docker"

        if engine in ("apptainer", "singularity"):
            container_ref = image
            if not Path(container_ref).exists() and not container_ref.startswith(
                ("docker://", "oras://", "shub://")
            ):
                container_ref = f"docker://{container_ref}"
            return [
                engine,
                "exec",
                "--nv",
                "-B",
                f"{Path.cwd()}:/workspace",
                container_ref,
                tool_name,
            ]
        else:
            gpu_args = ["--gpus", "all"]
            if os.environ.get("AIDD_INTERN_CPU_FALLBACK", "").lower() in ("1", "true"):
                gpu_args = []
            return [
                "docker",
                "run",
                "--rm",
                *gpu_args,
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


async def run_rfd3_handler(
    target_pdb: str,
    interface_residues: str | None = None,
    num_samples: int = 100,
    hotspot_residues: str | None = None,
    atom_precision: bool = True,
    tool_runtime: str = "local",
) -> dict[str, Any]:
    """Execute RFdiffusion3 (RFD3) atom-level diffusion and design."""
    target = _safe_path(target_pdb)
    gpu_plan = _gpu_plan("rfd3", num_samples=num_samples)
    if not gpu_plan["can_run"]:
        return _base_output("rfd3", [], 75, "", gpu_plan["reason"] or "", gpu_plan)
    num_samples = int(gpu_plan.get("num_samples", num_samples))
    command = [
        *_runtime_prefix("rfd3", tool_runtime),
        "generate",
        "--target-pdb",
        str(target),
        "--num-samples",
        str(num_samples),
    ]
    if interface_residues:
        command.extend(["--interface-residues", interface_residues])
    if hotspot_residues:
        command.extend(["--hotspot-residues", hotspot_residues])
    if atom_precision:
        command.append("--atom-precision")
    returncode, stdout, stderr = await _run_command(command)
    return _base_output("rfd3", command, returncode, stdout, stderr, gpu_plan)


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


async def _rfd3_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    result = await run_rfd3_handler(
        target_pdb=arguments["target_pdb"],
        interface_residues=arguments.get("interface_residues"),
        num_samples=int(arguments.get("num_samples") or 100),
        hotspot_residues=arguments.get("hotspot_residues"),
        atom_precision=bool(arguments.get("atom_precision", True)),
        tool_runtime=arguments.get("tool_runtime") or "local",
    )
    return _format_result(result), result["returncode"] == 0


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


async def _chai1_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    from agent.workflows.protein_design.validation import evaluate_with_chai1

    try:
        metrics = await evaluate_with_chai1(complex_pdb=arguments["complex_pdb"])
        return _format_result({"status": "completed", "metrics": metrics}), True
    except Exception as exc:
        return _format_result({"status": "failed", "error": str(exc)}), False


async def _protenix_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    from agent.workflows.protein_design.validation import evaluate_with_protenix

    try:
        metrics = await evaluate_with_protenix(complex_pdb=arguments["complex_pdb"])
        return _format_result({"status": "completed", "metrics": metrics}), True
    except Exception as exc:
        return _format_result({"status": "failed", "error": str(exc)}), False


# ---------------------------------------------------------------------------
# New tools: ProteinMPNN, ESMFold, Foldseek, Sequence Analysis
# (Adaptyv Bio competition inspired tool-chain expansion)
# ---------------------------------------------------------------------------


async def _proteinmpnn_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    """Design sequences for a backbone using ProteinMPNN."""
    backbone_pdb = arguments["backbone_pdb"]
    num_sequences = int(arguments.get("num_sequences") or 10)
    temperature = float(arguments.get("temperature") or 0.1)
    output_dir = arguments.get("output_dir") or os.path.dirname(backbone_pdb)
    chain_id = arguments.get("chain_id") or "A"
    seed = arguments.get("seed")

    cmd = [
        "python",
        "-m",
        "proteinmpnn",
        "--pdb_path",
        backbone_pdb,
        "--out_folder",
        output_dir,
        "--num_seq_per_target",
        str(num_sequences),
        "--sampling_temp",
        str(temperature),
        "--chain_list",
        chain_id,
    ]
    if seed is not None:
        cmd.extend(["--seed", str(seed)])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=int(arguments.get("timeout_s") or 600),
        )
        output = stdout.decode(errors="replace")
        errors = stderr.decode(errors="replace")
        combined = f"{output}\n{errors}".strip()
        if proc.returncode != 0:
            hw = _parse_hardware_errors(combined)
            return _format_result(
                {
                    "status": "failed",
                    "returncode": proc.returncode,
                    "output": combined[:MAX_TOOL_OUTPUT_CHARS],
                    "hardware_errors": hw,
                }
            ), False
        return _format_result(
            {
                "status": "completed",
                "output_dir": output_dir,
                "num_sequences": num_sequences,
                "output": combined[:MAX_TOOL_OUTPUT_CHARS],
            }
        ), True
    except asyncio.TimeoutError:
        return _format_result(
            {"status": "timeout", "timeout_s": arguments.get("timeout_s")}
        ), False
    except FileNotFoundError:
        return _format_result(
            {
                "status": "failed",
                "error": "ProteinMPNN not found. Install with: pip install proteinmpnn",
            }
        ), False
    except Exception as exc:
        return _format_result({"status": "failed", "error": str(exc)}), False


async def _esmfold_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    """Predict structure from sequence using ESMFold."""
    sequence = arguments["sequence"]
    output_pdb = arguments.get("output_pdb") or "esmfold_output.pdb"

    try:
        # Use ESMFold via Python API (preferred over CLI for single sequences)
        script = (
            "import torch\n"
            "from esm import pretrained\n"
            f"model, alphabet = pretrained.load_model_and_alphabet('esmfold_v1')\n"
            "model = model.eval().cuda()\n"
            f"sequence = '{sequence}'\n"
            "with torch.no_grad():\n"
            "    output = model.infer_pdb(sequence)\n"
            f"with open('{output_pdb}', 'w') as f:\n"
            "    f.write(output['pdb_string'][0])\n"
            "print('ESMFold prediction completed')\n"
            "print(f'pLDDT: {output[\"plddt\"].mean().item():.2f}')\n"
            "print(f'pTM: {output[\"ptm\"].item():.2f}')\n"
        )
        proc = await asyncio.create_subprocess_exec(
            "python",
            "-c",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=int(arguments.get("timeout_s") or 600),
        )
        output = stdout.decode(errors="replace")
        errors = stderr.decode(errors="replace")
        combined = f"{output}\n{errors}".strip()
        if proc.returncode != 0:
            hw = _parse_hardware_errors(combined)
            return _format_result(
                {
                    "status": "failed",
                    "returncode": proc.returncode,
                    "output": combined[:MAX_TOOL_OUTPUT_CHARS],
                    "hardware_errors": hw,
                }
            ), False
        return _format_result(
            {
                "status": "completed",
                "output_pdb": output_pdb,
                "output": combined[:MAX_TOOL_OUTPUT_CHARS],
            }
        ), True
    except asyncio.TimeoutError:
        return _format_result(
            {"status": "timeout", "timeout_s": arguments.get("timeout_s")}
        ), False
    except Exception as exc:
        return _format_result({"status": "failed", "error": str(exc)}), False


async def _foldseek_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    """Cluster or search protein structures using Foldseek."""
    mode = arguments.get("mode") or "cluster"
    input_path = arguments["input_path"]
    output_path = arguments.get("output_path") or "foldseek_output"
    min_seq_id = float(arguments.get("min_seq_id") or 0.3)

    if mode == "cluster":
        cmd = [
            "foldseek",
            "easy-cluster",
            input_path,
            output_path,
            "tmp",
            "--min-seq-id",
            str(min_seq_id),
            "-e",
            "0.001",
            "--alignment-type",
            "1",  # 3Di alignment
        ]
    elif mode == "search":
        db_path = arguments.get("db_path")
        if not db_path:
            return _format_result(
                {"status": "failed", "error": "db_path required for search mode"}
            ), False
        cmd = [
            "foldseek",
            "easy-search",
            input_path,
            db_path,
            output_path,
            "tmp",
            "-e",
            "0.001",
            "--alignment-type",
            "1",
        ]
    elif mode == "createdb":
        cmd = ["foldseek", "createdb", input_path, output_path]
    else:
        return _format_result(
            {"status": "failed", "error": f"Unknown mode: {mode}"}
        ), False

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=int(arguments.get("timeout_s") or 300),
        )
        output = stdout.decode(errors="replace")
        errors = stderr.decode(errors="replace")
        combined = f"{output}\n{errors}".strip()
        if proc.returncode != 0:
            return _format_result(
                {
                    "status": "failed",
                    "returncode": proc.returncode,
                    "output": combined[:MAX_TOOL_OUTPUT_CHARS],
                }
            ), False
        return _format_result(
            {
                "status": "completed",
                "mode": mode,
                "output_path": output_path,
                "output": combined[:MAX_TOOL_OUTPUT_CHARS],
            }
        ), True
    except asyncio.TimeoutError:
        return _format_result(
            {"status": "timeout", "timeout_s": arguments.get("timeout_s")}
        ), False
    except FileNotFoundError:
        return _format_result(
            {
                "status": "failed",
                "error": "Foldseek not found. Install: https://github.com/steineggerlab/foldseek",
            }
        ), False
    except Exception as exc:
        return _format_result({"status": "failed", "error": str(exc)}), False


async def _sequence_analysis_tool(arguments: dict[str, Any]) -> tuple[str, bool]:
    """Analyse protein sequence properties: hydrophobicity, charge, aggregation, ESM2 PLL."""
    sequence = arguments["sequence"]
    analyses = arguments.get("analyses") or [
        "hydrophobicity",
        "charge",
        "aggregation",
        "esm2_pll",
    ]
    if isinstance(analyses, str):
        analyses = [a.strip() for a in analyses.split(",")]

    results: dict[str, Any] = {"sequence_length": len(sequence)}

    # Hydrophobicity (Kyte-Doolittle scale)
    if "hydrophobicity" in analyses:
        kd_scale = {
            "A": 1.8,
            "R": -4.5,
            "N": -3.5,
            "D": -3.5,
            "C": 2.5,
            "Q": -3.5,
            "E": -3.5,
            "G": -0.4,
            "H": -3.2,
            "I": 4.5,
            "L": 3.8,
            "K": -3.9,
            "M": 1.9,
            "F": 2.8,
            "P": -1.6,
            "S": -0.8,
            "T": -0.7,
            "W": -0.9,
            "Y": -1.3,
            "V": 4.2,
        }
        scores = [
            kd_scale.get(aa.upper(), 0.0) for aa in sequence if aa.upper() in kd_scale
        ]
        avg_hydro = sum(scores) / len(scores) if scores else 0.0
        results["hydrophobicity"] = {
            "average_gravy": round(avg_hydro, 3),
            "interpretation": "hydrophobic" if avg_hydro > 0 else "hydrophilic",
        }

    # Charge at pH 7.0
    if "charge" in analyses:
        pos = sum(1 for aa in sequence.upper() if aa in ("K", "R", "H"))
        neg = sum(1 for aa in sequence.upper() if aa in ("D", "E"))
        net_charge = pos - neg
        results["charge"] = {
            "positive_residues": pos,
            "negative_residues": neg,
            "net_charge_at_ph7": net_charge,
            "charge_density": round(net_charge / len(sequence), 3) if sequence else 0,
        }

    # Aggregation propensity (simplified Tango-like heuristic)
    if "aggregation" in analyses:
        hydro_stretch = 0
        max_stretch = 0
        for aa in sequence.upper():
            if aa in ("V", "I", "L", "F", "W", "Y", "A"):
                hydro_stretch += 1
                max_stretch = max(max_stretch, hydro_stretch)
            else:
                hydro_stretch = 0
        results["aggregation"] = {
            "max_hydrophobic_stretch": max_stretch,
            "aggregation_risk": "high"
            if max_stretch >= 7
            else "moderate"
            if max_stretch >= 5
            else "low",
        }

    # ESM2 pseudo-log-likelihood (PLL)
    if "esm2_pll" in analyses:
        try:
            script = (
                "import torch\n"
                "from esm import pretrained\n"
                "model, alphabet = pretrained.load_model_and_alphabet('esm2_t33_650M_UR50D')\n"
                "model = model.eval()\n"
                f"seq = '{sequence}'\n"
                "batch_converter = alphabet.get_batch_converter()\n"
                "data = [('seq', seq)]\n"
                "_, _, batch_tokens = batch_converter(data)\n"
                "with torch.no_grad():\n"
                "    logits = model(batch_tokens)['logits']\n"
                "    log_probs = logits.log_softmax(-1)\n"
                "    token_probs = log_probs.gather(-1, batch_tokens.unsqueeze(-1)).squeeze(-1)\n"
                "    pll = token_probs[0, 1:-1].sum().item()\n"
                f"print(f'PLL:{{pll:.4f}}')\n"
            )
            proc = await asyncio.create_subprocess_exec(
                "python",
                "-c",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            import re as _re

            pll_match = _re.search(r"PLL:([-0-9.]+)", stdout.decode())
            if pll_match:
                results["esm2_pll"] = {"pll": float(pll_match.group(1))}
            else:
                results["esm2_pll"] = {"error": "Could not parse PLL output"}
        except Exception as exc:
            results["esm2_pll"] = {"error": str(exc)}

    return _format_result({"status": "completed", "analyses": results}), True


def create_protein_design_tools(tool_spec_cls: type | None = None) -> list[Any]:
    """Create ToolSpec instances for protein-design workflows."""
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
        tool_spec_cls(
            name="run_chai1",
            description=(
                "Evaluate a protein-binder complex structure using Chai-1. "
                "Calculates orthogonal validation metrics: ipTM, pLDDT, and pAE."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "complex_pdb": {
                        "type": "string",
                        "description": "Path to the complex PDB file to evaluate.",
                    }
                },
                "required": ["complex_pdb"],
            },
            handler=_chai1_tool,
        ),
        tool_spec_cls(
            name="run_protenix",
            description=(
                "Evaluate a protein-binder complex structure using Protenix as an "
                "orthogonal validation model. Calculates ipTM, pLDDT, and pAE."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "complex_pdb": {
                        "type": "string",
                        "description": "Path to the complex PDB file to evaluate.",
                    }
                },
                "required": ["complex_pdb"],
            },
            handler=_protenix_tool,
        ),
        tool_spec_cls(
            name="run_proteinmpnn",
            description=(
                "Design amino acid sequences for a given protein backbone using ProteinMPNN. "
                "Useful for sequence optimization of designed binders."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "backbone_pdb": {
                        "type": "string",
                        "description": "Path to backbone PDB file.",
                    },
                    "num_sequences": {
                        "type": "integer",
                        "default": 10,
                        "description": "Number of sequences to generate per backbone.",
                    },
                    "temperature": {
                        "type": "number",
                        "default": 0.1,
                        "description": "Sampling temperature (lower = more conservative).",
                    },
                    "chain_id": {
                        "type": "string",
                        "default": "A",
                        "description": "Chain ID to design.",
                    },
                    "seed": {
                        "type": "integer",
                        "description": "Random seed for reproducibility.",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory for designed sequences.",
                    },
                    "timeout_s": {
                        "type": "integer",
                        "description": "Command timeout in seconds.",
                    },
                },
                "required": ["backbone_pdb"],
            },
            handler=_proteinmpnn_tool,
        ),
        tool_spec_cls(
            name="run_esmfold",
            description=(
                "Predict 3D structure from amino acid sequence using ESMFold. "
                "Fast single-sequence structure prediction without MSA."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "sequence": {
                        "type": "string",
                        "description": "Amino acid sequence (single-letter code).",
                    },
                    "output_pdb": {
                        "type": "string",
                        "description": "Output PDB file path.",
                    },
                    "timeout_s": {
                        "type": "integer",
                        "description": "Command timeout in seconds.",
                    },
                },
                "required": ["sequence"],
            },
            handler=_esmfold_tool,
        ),
        tool_spec_cls(
            name="run_foldseek",
            description=(
                "Cluster or search protein structures using Foldseek. "
                "Modes: 'cluster' for structure clustering, 'search' for structure search, "
                "'createdb' for creating a Foldseek database."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "input_path": {
                        "type": "string",
                        "description": "Path to input PDB file(s) or directory.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["cluster", "search", "createdb"],
                        "default": "cluster",
                        "description": "Foldseek operation mode.",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Output path for results.",
                    },
                    "min_seq_id": {
                        "type": "number",
                        "default": 0.3,
                        "description": "Minimum sequence identity for clustering.",
                    },
                    "db_path": {
                        "type": "string",
                        "description": "Database path (required for search mode).",
                    },
                    "timeout_s": {
                        "type": "integer",
                        "description": "Command timeout in seconds.",
                    },
                },
                "required": ["input_path"],
            },
            handler=_foldseek_tool,
        ),
        tool_spec_cls(
            name="run_sequence_analysis",
            description=(
                "Analyse protein sequence properties including hydrophobicity (GRAVY), "
                "net charge at pH 7, aggregation propensity, and ESM2 pseudo-log-likelihood (PLL). "
                "Use for quality assessment of designed sequences."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "sequence": {
                        "type": "string",
                        "description": "Amino acid sequence (single-letter code).",
                    },
                    "analyses": {
                        "type": "string",
                        "description": (
                            "Comma-separated list of analyses to run. "
                            "Options: hydrophobicity, charge, aggregation, esm2_pll. "
                            "Default: all."
                        ),
                    },
                },
                "required": ["sequence"],
            },
            handler=_sequence_analysis_tool,
        ),
    ]
