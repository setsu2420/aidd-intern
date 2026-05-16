#!/usr/bin/env python3
"""FastMCP wrapper for local PXDesign CLI usage.

This server intentionally does not depend on Docker. It discovers a local
``pxdesign`` executable and exposes a small async job interface suitable for
long-running protein design jobs.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


mcp = FastMCP(name="pxdesign")
JOBS: dict[str, dict[str, Any]] = {}


def _pxdesign_cmd() -> list[str] | None:
    configured = os.environ.get("PXDESIGN_BIN")
    if configured:
        return shlex.split(configured)
    executable = shutil.which("pxdesign")
    if executable:
        return [executable]
    conda_env = os.environ.get("PXDESIGN_CONDA_ENV", "pxdesign")
    if shutil.which("conda"):
        return ["conda", "run", "-n", conda_env, "pxdesign"]
    return None


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    repo_dir = env.get("PXDESIGN_REPO_DIR")
    if repo_dir:
        env["PYTHONPATH"] = (
            repo_dir if not env.get("PYTHONPATH") else f"{repo_dir}:{env['PYTHONPATH']}"
        )
    return env


def _tail(path: Path, lines: int = 80) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-lines:])


def _poll_job(job: dict[str, Any]) -> None:
    process: subprocess.Popen[str] | None = job.get("process")
    if process is None:
        return
    returncode = process.poll()
    if returncode is None:
        job["status"] = "running"
        return
    job["returncode"] = returncode
    job["finished_at"] = job.get("finished_at") or time.time()
    job["status"] = "completed" if returncode == 0 else "failed"
    job["process"] = None


@mcp.tool
def pxdesign_status() -> dict[str, Any]:
    """Check whether PXDesign is installed and visible to this MCP server."""
    base_cmd = _pxdesign_cmd()
    result: dict[str, Any] = {
        "available": base_cmd is not None,
        "command": shlex.join(base_cmd) if base_cmd else None,
        "repo_dir": os.environ.get("PXDESIGN_REPO_DIR"),
        "active_jobs": len([j for j in JOBS.values() if j.get("status") == "running"]),
    }
    if not base_cmd:
        result["message"] = (
            "PXDesign CLI was not found. Run scripts/setup-proteinmcp-local.sh "
            "pxdesign_mcp, or set PXDESIGN_BIN to the pxdesign executable."
        )
        return result

    try:
        completed = subprocess.run(
            [*base_cmd, "--help"],
            env=_base_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
            check=False,
        )
        result["returncode"] = completed.returncode
        result["help_preview"] = completed.stdout[:2000]
    except Exception as exc:
        result["available"] = False
        result["error"] = str(exc)
    return result


@mcp.tool
def pxdesign_submit(
    input_yaml: str,
    output_dir: str,
    preset: str = "extended",
    n_sample: int = 10,
    dtype: str = "bf16",
    use_fast_ln: bool = True,
    use_deepspeed_evo_attention: bool = True,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Submit a PXDesign pipeline job and return immediately.

    Parameters mirror common PXDesign pipeline flags. Use extra_args for
    project-specific flags not yet modeled by this wrapper.
    """
    base_cmd = _pxdesign_cmd()
    if not base_cmd:
        return {
            "status": "error",
            "message": (
                "PXDesign CLI was not found. Run scripts/setup-proteinmcp-local.sh "
                "pxdesign_mcp, or set PXDESIGN_BIN."
            ),
        }

    input_path = Path(input_yaml).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    if not input_path.exists():
        return {
            "status": "error",
            "message": f"input_yaml does not exist: {input_path}",
        }
    output_path.mkdir(parents=True, exist_ok=True)
    log_path = output_path / "pxdesign_run.log"

    cmd = [
        *base_cmd,
        "pipeline",
        "--input_yaml",
        str(input_path),
        "--outdir",
        str(output_path),
        "--preset",
        preset,
        "--n_sample",
        str(n_sample),
        "--dtype",
        dtype,
        "--use_fast_ln",
        str(use_fast_ln),
        "--use_deepspeed_evo_attention",
        str(use_deepspeed_evo_attention),
    ]
    if extra_args:
        cmd.extend(extra_args)

    log_handle = log_path.open("a", encoding="utf-8")
    log_handle.write(f"\n# {time.strftime('%Y-%m-%d %H:%M:%S')} starting\n")
    log_handle.write(f"$ {shlex.join(cmd)}\n")
    log_handle.flush()

    process = subprocess.Popen(
        cmd,
        cwd=str(output_path),
        env=_base_env(),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    job_id = f"pxdesign-{uuid.uuid4().hex[:12]}"
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "pid": process.pid,
        "process": process,
        "command": cmd,
        "input_yaml": str(input_path),
        "output_dir": str(output_path),
        "log_file": str(log_path),
        "started_at": time.time(),
    }
    return {
        "status": "submitted",
        "job_id": job_id,
        "pid": process.pid,
        "output_dir": str(output_path),
        "log_file": str(log_path),
        "command": shlex.join(cmd),
    }


@mcp.tool
def pxdesign_check_status(
    job_id: str | None = None, output_dir: str | None = None
) -> dict[str, Any]:
    """Check a PXDesign job by job_id, or inspect an output directory log."""
    if job_id:
        job = JOBS.get(job_id)
        if not job:
            return {"status": "not_found", "message": f"unknown job_id: {job_id}"}
        _poll_job(job)
        log_file = Path(job["log_file"])
        return {key: value for key, value in job.items() if key != "process"} | {
            "log_tail": _tail(log_file)
        }

    if output_dir:
        output_path = Path(output_dir).expanduser().resolve()
        log_file = output_path / "pxdesign_run.log"
        if not output_path.exists():
            return {
                "status": "not_found",
                "message": f"output_dir does not exist: {output_path}",
            }
        return {
            "status": "inspected",
            "output_dir": str(output_path),
            "log_file": str(log_file),
            "log_tail": _tail(log_file),
        }

    return {"status": "error", "message": "Provide either job_id or output_dir."}


@mcp.tool
def pxdesign_cancel_job(job_id: str) -> dict[str, Any]:
    """Terminate a running PXDesign job submitted by this MCP server."""
    job = JOBS.get(job_id)
    if not job:
        return {"status": "not_found", "message": f"unknown job_id: {job_id}"}
    _poll_job(job)
    process: subprocess.Popen[str] | None = job.get("process")
    if process is None:
        return {"status": job["status"], "message": "job is no longer running"}
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=15)
    _poll_job(job)
    return {
        "status": "cancelled",
        "job_id": job_id,
        "returncode": job.get("returncode"),
    }


if __name__ == "__main__":
    mcp.run()
