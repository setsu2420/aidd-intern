import json
from pathlib import Path

import pytest

from agent.core import agent_loop
from agent.core.tools import create_builtin_tools
from agent.workflows.protein_design.ace import ace_playbook_handler
from agent.workflows.protein_design.approval import ProteinDesignApprovalPolicy
from agent.workflows.protein_design.telemetry import summarize_validation_metrics
from agent.workflows.protein_design.tools import (
    _gpu_plan,
    _parse_hardware_errors,
    _run_command,
    run_bindcraft_handler,
)
from evals.protein_design.runner import (
    EvaluationTask,
    run_evaluation_suite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_protein_design_tools_are_registered_for_llm():
    tools = create_builtin_tools(local_mode=True)
    specs = {tool.name: tool for tool in tools}

    assert "run_pxdesign" in specs
    assert "run_boltzgen" in specs
    assert "run_bindcraft" in specs
    assert "run_rfd3" in specs
    assert "protein_design_ace_playbook" in specs
    assert "target_pdb" in specs["run_pxdesign"].parameters["required"]
    assert "target_pdb" in specs["run_rfd3"].parameters["required"]


def test_protein_design_oom_parser_detects_cuda_oom():
    parsed = _parse_hardware_errors("RuntimeError: CUDA out of memory")

    assert parsed["cuda_oom"] is True
    assert "mixed precision" in parsed["suggested_correction"]


def test_protein_design_gpu_plan_downscales_samples(monkeypatch):
    monkeypatch.setenv("PROTEIN_DESIGN_GPU_FREE_MB", "12000")

    plan = _gpu_plan("pxdesign", num_samples=100)

    assert plan["can_run"] is True
    assert plan["adjusted"] is True
    assert plan["num_samples"] < 100
    assert "Downscaled" in plan["reason"]


def test_protein_design_gpu_plan_blocks_tiny_gpu(monkeypatch):
    monkeypatch.setenv("PROTEIN_DESIGN_GPU_FREE_MB", "4000")

    plan = _gpu_plan("boltzgen", num_samples=1)

    assert plan["can_run"] is False
    assert "Insufficient free GPU memory" in plan["reason"]


@pytest.mark.asyncio
async def test_protein_design_approval_policy_thresholds():
    policy = ProteinDesignApprovalPolicy()

    assert await policy.decide("run_pxdesign", {"num_samples": 201}, None)
    assert not await policy.decide("run_pxdesign", {"num_samples": 200}, None)
    assert await policy.decide("run_rfd3", {"num_samples": 201}, None)
    assert not await policy.decide("run_rfd3", {"num_samples": 200}, None)
    assert await policy.decide("run_bindcraft", {"iterations": 101}, None)


def test_core_approval_policy_covers_protein_design_tools():
    assert agent_loop._needs_approval("run_pxdesign", {"num_samples": 250})
    assert agent_loop._needs_approval("run_boltzgen", {"num_samples": 250})
    assert agent_loop._needs_approval("run_rfd3", {"num_samples": 250})
    assert not agent_loop._needs_approval("run_rfd3", {"num_samples": 200})
    assert agent_loop._needs_approval("run_bindcraft", {"iterations": 101})
    assert not agent_loop._needs_approval("run_bindcraft", {"iterations": 100})


@pytest.mark.asyncio
async def test_run_command_reports_missing_executable():
    returncode, stdout, stderr = await _run_command(
        ["definitely-not-a-real-protein-design-command"]
    )

    assert returncode == 127
    assert stdout == ""
    assert "Executable not found" in stderr


@pytest.mark.asyncio
async def test_run_bindcraft_uses_local_mcp_runtime(tmp_path, monkeypatch):
    mcp_root = tmp_path / "bindcraft_mcp"
    env_python = mcp_root / "env/bin/python"
    script = mcp_root / "scripts/run_bindcraft.py"
    filters = mcp_root / "repo/BindCraft/settings_filters/default_filters.json"
    advanced = (
        mcp_root / "repo/BindCraft/settings_advanced/default_4stage_multimer.json"
    )
    params = mcp_root / "repo/scripts/params"
    for path in [
        env_python,
        script,
        filters,
        advanced,
        params / "params_model_1_multimer_v3.npz",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "", encoding="utf-8")
    advanced.write_text('{"af_params_dir": ""}\n', encoding="utf-8")

    target = tmp_path / "target.pdb"
    target.write_text("HEADER TARGET\n", encoding="utf-8")
    output = tmp_path / "out"
    captured = {}

    async def fake_run_command(command, timeout_s=None, cwd=None, env=None):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        return 0, "done", ""

    monkeypatch.setenv("AIDD_INTERN_BINDCRAFT_MCP_DIR", str(mcp_root))
    monkeypatch.setenv("PROTEIN_DESIGN_GPU_FREE_MB", "12000,64000")
    monkeypatch.setattr(
        "agent.workflows.protein_design.tools._run_command",
        fake_run_command,
    )

    result = await run_bindcraft_handler(
        target_pdb=str(target),
        binder_length=80,
        output_dir=str(output),
        hotspot_residues="1,2,3",
        num_designs=1,
        max_trajectories=4,
    )

    assert result["returncode"] == 0
    assert result["output_dir"] == str(output)
    assert captured["command"][0] == str(env_python)
    assert captured["cwd"] == str(mcp_root / "scripts")
    assert captured["env"]["CUDA_VISIBLE_DEVICES"] == "1"
    settings = json.loads((output / "target_settings.json").read_text())
    generated_advanced = json.loads(
        (output / "aidd_advanced_settings.json").read_text()
    )
    assert settings["target_hotspot_residues"] == "1,2,3"
    assert generated_advanced["af_params_dir"] == str(params)
    assert generated_advanced["save_design_animations"] is False
    assert generated_advanced["zip_animations"] is False
    assert generated_advanced["max_trajectories"] == 4


def test_protein_design_telemetry_summarizes_terminal_filters():
    summary = summarize_validation_metrics(
        [
            {"iptm": 0.85, "plddt": 88, "fold_cluster": "a"},
            {"iptm": 0.77, "plddt": 91, "fold_cluster": "b"},
            {"iptm": 0.91, "plddt": 82, "fold_cluster": "a"},
        ]
    )

    assert summary["candidate_count"] == 3
    assert summary["passing_count"] == 2
    assert summary["fold_clusters"] == 1


def test_pd_l1_design_report_contains_required_sections():
    report = (PROJECT_ROOT / "docs" / "pd-l1-binder-design-report.md").read_text(
        encoding="utf-8"
    )
    required_sections = [
        "## 1. Executive Design Summary",
        "## 2. Structural Biology Deep Dive",
        "## 3. PD-1 / PD-L1 Interface Analysis",
        "## 4. Epitope Intelligence",
        "## 5. Glycosylation & PTM Analysis",
        "## 6. Existing Therapeutic Landscape",
        "## 7. Computational Design Strategy Recommendations",
        "## 8. Failure Modes & Risks",
        "## 9. Hypothesis-Driven Binder Design Ideas",
        "## 10. Benchmark & Evaluation Suggestions",
        "## 11. Open Questions & Future Directions",
    ]

    for section in required_sections:
        assert section in report

    for design_term in ["4ZQK", "5X8M", "5XXY", "5GRJ", "5JDS", "5J89"]:
        assert design_term in report


@pytest.mark.asyncio
async def test_ace_playbook_applies_delta_and_merges_duplicates(tmp_path):
    playbook_path = tmp_path / "ace_playbook.json"

    text, ok = await ace_playbook_handler(
        {
            "operation": "apply_delta",
            "playbook_path": str(playbook_path),
            "delta_items": [
                {
                    "section": "failure_modes",
                    "content": "Reduce PXdesign samples after CUDA OOM.",
                    "feedback": "helpful",
                    "source": "reflector",
                    "evidence": {"tool": "run_pxdesign"},
                },
                {
                    "section": "failure_modes",
                    "content": "Reduce PXdesign samples after CUDA OOM.",
                    "feedback": "helpful",
                    "source": "curator",
                },
            ],
        }
    )

    assert ok is True
    assert '"delta_count": 2' in text

    rendered, ok = await ace_playbook_handler(
        {"operation": "render", "playbook_path": str(playbook_path)}
    )

    assert ok is True
    assert rendered.count("Reduce PXdesign samples after CUDA OOM.") == 1
    assert "h=2" in rendered


@pytest.mark.asyncio
async def test_ace_playbook_reflects_run_feedback(tmp_path):
    playbook_path = tmp_path / "ace_playbook.json"

    text, ok = await ace_playbook_handler(
        {
            "operation": "reflect_run",
            "playbook_path": str(playbook_path),
            "tool_name": "run_pxdesign",
            "status": "failed",
            "stderr": "RuntimeError: CUDA out of memory",
            "metrics": {"iptm": 0.61, "plddt": 77},
        }
    )

    assert ok is True
    payload = json.loads(text)
    assert payload["status"] == "reflected"
    assert payload["delta_count"] >= 2

    rendered, ok = await ace_playbook_handler(
        {"operation": "render", "playbook_path": str(playbook_path)}
    )

    assert ok is True
    assert "CUDA OOM" in rendered
    assert "Harness Feedback" in rendered


@pytest.mark.asyncio
async def test_protein_design_eval_runner_emits_harness_feedback(tmp_path):
    target = tmp_path / "target.pdb"
    target.write_text("HEADER TEST\n", encoding="utf-8")
    task = EvaluationTask(
        task_id="toy_target",
        target_name="Toy",
        target_pdb_path=str(target),
        known_hotspots="chain A: Y1",
    )

    results = await run_evaluation_suite([task], "test-model")

    result = results[0]
    assert result["harness_ready"] is True
    assert result["harness_profile"]["schema"] == "ETCLOVG"
    assert result["status"] == "ready_for_headless_agent"
    assert result["feedback_delta_items"][0]["section"] == "harness_feedback"


@pytest.mark.asyncio
async def test_protein_design_eval_runner_blocks_missing_environment():
    task = EvaluationTask(
        task_id="missing_target",
        target_name="Missing",
        target_pdb_path="/tmp/aidd-intern-missing-target.pdb",
        known_hotspots="chain A: Y1",
    )

    results = await run_evaluation_suite([task], "test-model")

    result = results[0]
    assert result["harness_ready"] is False
    assert result["status"] == "skipped_missing_target"
    assert "environment" in result["feedback_delta_items"][0]["content"]
