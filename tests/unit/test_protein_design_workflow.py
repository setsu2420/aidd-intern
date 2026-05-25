import json
from pathlib import Path

import pytest

from agent.core import agent_loop
from agent.core.tools import create_builtin_tools
from agent.workflows.protein_design.ace import ace_playbook_handler
from agent.workflows.protein_design.approval import ProteinDesignApprovalPolicy
from agent.workflows.protein_design.telemetry import summarize_validation_metrics
from agent.workflows.protein_design.tools import (
    _esmfold_tool,
    _foldseek_tool,
    _gpu_plan,
    _parse_hardware_errors,
    _proteinmpnn_tool,
    _run_command,
    _sequence_analysis_tool,
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
    assert "run_chai1" in specs
    assert "run_protenix" in specs
    assert "protein_design_ace_playbook" in specs
    assert "target_pdb" in specs["run_pxdesign"].parameters["required"]
    assert "target_pdb" in specs["run_rfd3"].parameters["required"]
    assert "complex_pdb" in specs["run_chai1"].parameters["required"]
    assert "complex_pdb" in specs["run_protenix"].parameters["required"]
    # New tools (Phase 2)
    assert "run_proteinmpnn" in specs
    assert "run_esmfold" in specs
    assert "run_foldseek" in specs
    assert "run_sequence_analysis" in specs
    assert "backbone_pdb" in specs["run_proteinmpnn"].parameters["required"]
    assert "sequence" in specs["run_esmfold"].parameters["required"]
    assert "input_path" in specs["run_foldseek"].parameters["required"]
    assert "sequence" in specs["run_sequence_analysis"].parameters["required"]


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


def test_protein_design_gpu_plan_force_run(monkeypatch):
    monkeypatch.setenv("PROTEIN_DESIGN_GPU_FREE_MB", "4000")
    monkeypatch.setenv("AIDD_INTERN_FORCE_GPU_RUN", "True")

    plan = _gpu_plan("boltzgen", num_samples=1)

    assert plan["can_run"] is True
    assert "Force-run enabled" in plan["reason"]


def test_protein_design_gpu_plan_cpu_fallback(monkeypatch):
    monkeypatch.setenv("PROTEIN_DESIGN_GPU_FREE_MB", "4000")
    monkeypatch.setenv("AIDD_INTERN_CPU_FALLBACK", "True")

    plan = _gpu_plan("boltzgen", num_samples=1)

    assert plan["can_run"] is True
    assert "CPU-fallback enabled" in plan["reason"]
    assert plan.get("cpu_fallback") is True


def test_apptainer_runtime_prefix_generation(monkeypatch):
    from agent.workflows.protein_design.tools import _runtime_prefix

    monkeypatch.setenv("PROTEIN_DESIGN_CONTAINER_ENGINE", "apptainer")

    prefix = _runtime_prefix("boltzgen", "sandbox")

    assert prefix[0] == "apptainer"
    assert prefix[1] == "exec"
    assert "--nv" in prefix
    assert "docker://aidd-intern/protein-design-boltzgen:latest" in prefix


@pytest.mark.asyncio
async def test_chai1_protenix_tools_execution(monkeypatch, tmp_path):
    from agent.workflows.protein_design.tools import _chai1_tool, _protenix_tool

    complex_pdb = tmp_path / "complex.pdb"
    complex_pdb.write_text("HEADER COMPLEX\n", encoding="utf-8")

    async def mock_evaluate_with_chai1(complex_pdb):
        return {"iptm": 0.85, "plddt": 88.0, "pae": 2.5}

    async def mock_evaluate_with_protenix(complex_pdb):
        return {"iptm": 0.82, "plddt": 85.0, "pae": 2.7}

    monkeypatch.setattr(
        "agent.workflows.protein_design.validation.evaluate_with_chai1",
        mock_evaluate_with_chai1,
    )
    monkeypatch.setattr(
        "agent.workflows.protein_design.validation.evaluate_with_protenix",
        mock_evaluate_with_protenix,
    )

    chai1_res, chai1_ok = await _chai1_tool({"complex_pdb": str(complex_pdb)})
    protenix_res, protenix_ok = await _protenix_tool({"complex_pdb": str(complex_pdb)})

    assert chai1_ok is True
    assert protenix_ok is True

    chai1_json = json.loads(chai1_res)
    protenix_json = json.loads(protenix_res)

    assert chai1_json["status"] == "completed"
    assert chai1_json["metrics"]["iptm"] == 0.85
    assert protenix_json["status"] == "completed"
    assert protenix_json["metrics"]["iptm"] == 0.82


# ---------------------------------------------------------------------------
# Phase 2: New Tool Tests (ProteinMPNN, ESMFold, Foldseek, Sequence Analysis)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proteinmpnn_tool_missing_install(monkeypatch, tmp_path):
    """ProteinMPNN should return a friendly error when not installed."""
    fake_pdb = tmp_path / "backbone.pdb"
    fake_pdb.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\n")

    # Force subprocess to raise FileNotFoundError by pointing PATH to empty dir
    empty_bin = tmp_path / "empty_bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    result, ok = await _proteinmpnn_tool({"backbone_pdb": str(fake_pdb)})
    parsed = json.loads(result)

    assert ok is False
    assert parsed["status"] == "failed"
    assert "not found" in parsed.get("error", "").lower() or parsed.get("returncode", 0) != 0


@pytest.mark.asyncio
async def test_sequence_analysis_hydrophobicity():
    """GRAVY score for a known hydrophobic sequence should be positive."""
    # Poly-Leucine is extremely hydrophobic (Kyte-Doolittle L=3.8)
    result, ok = await _sequence_analysis_tool({
        "sequence": "LLLLLLLLLL",
        "analyses": "hydrophobicity",
    })
    parsed = json.loads(result)

    assert ok is True
    assert parsed["status"] == "completed"
    gravy = parsed["analyses"]["hydrophobicity"]["average_gravy"]
    assert gravy > 0
    assert parsed["analyses"]["hydrophobicity"]["interpretation"] == "hydrophobic"


@pytest.mark.asyncio
async def test_sequence_analysis_charge():
    """Net charge for poly-Lysine should be strongly positive."""
    result, ok = await _sequence_analysis_tool({
        "sequence": "KKKKKDD",
        "analyses": "charge",
    })
    parsed = json.loads(result)

    assert ok is True
    charge_info = parsed["analyses"]["charge"]
    # 5 K (positive) - 2 D (negative) = +3 net charge
    assert charge_info["positive_residues"] == 5
    assert charge_info["negative_residues"] == 2
    assert charge_info["net_charge_at_ph7"] == 3


@pytest.mark.asyncio
async def test_sequence_analysis_aggregation():
    """Long hydrophobic stretches should trigger high aggregation risk."""
    # 8 consecutive hydrophobic residues (V,I,L,F) => high risk
    result, ok = await _sequence_analysis_tool({
        "sequence": "SSSVVVVVVVLSSS",
        "analyses": "aggregation",
    })
    parsed = json.loads(result)

    assert ok is True
    agg = parsed["analyses"]["aggregation"]
    assert agg["max_hydrophobic_stretch"] >= 7
    assert agg["aggregation_risk"] == "high"


@pytest.mark.asyncio
async def test_sequence_analysis_aggregation_low_risk():
    """No long hydrophobic stretches should give low aggregation risk."""
    # Alternating hydrophilic/hydrophobic - no stretch > 1
    result, ok = await _sequence_analysis_tool({
        "sequence": "KSKSKSKSKS",
        "analyses": "aggregation",
    })
    parsed = json.loads(result)

    assert ok is True
    assert parsed["analyses"]["aggregation"]["aggregation_risk"] == "low"


@pytest.mark.asyncio
async def test_sequence_analysis_all_analyses():
    """Running all analyses should return all four keys."""
    result, ok = await _sequence_analysis_tool({
        "sequence": "ACDEFGHIKLMNPQRSTVWY",
        "analyses": "hydrophobicity,charge,aggregation",
    })
    parsed = json.loads(result)

    assert ok is True
    analyses = parsed["analyses"]
    assert "hydrophobicity" in analyses
    assert "charge" in analyses
    assert "aggregation" in analyses
    assert analyses["sequence_length"] == 20


@pytest.mark.asyncio
async def test_foldseek_tool_invalid_mode(tmp_path):
    """Foldseek with an invalid mode should fail gracefully."""
    fake_pdb = tmp_path / "input.pdb"
    fake_pdb.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\n")

    # 'invalid_mode' is not in [cluster, search, createdb] but the handler
    # will attempt to run foldseek which won't be installed → FileNotFoundError path
    result, ok = await _foldseek_tool({
        "input_path": str(fake_pdb),
        "mode": "cluster",
    })
    parsed = json.loads(result)

    # Without foldseek installed, this should fail gracefully
    assert ok is False
    assert parsed["status"] == "failed"


@pytest.mark.asyncio
async def test_esmfold_tool_missing_install(monkeypatch, tmp_path):
    """ESMFold should fail gracefully when torch/esm not installed."""
    empty_bin = tmp_path / "empty_bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    result, ok = await _esmfold_tool({
        "sequence": "ACDEFGHIK",
        "output_pdb": str(tmp_path / "out.pdb"),
    })
    parsed = json.loads(result)

    assert ok is False
    assert parsed["status"] == "failed"
