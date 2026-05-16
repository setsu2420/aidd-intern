import json
from pathlib import Path

import pytest

from agent import config as config_module
from agent.core import agent_loop
from agent.core.tools import create_builtin_tools
from agent.domain_packs.protein_design.ace import ace_playbook_handler
from agent.domain_packs.protein_design.approval import ProteinDesignApprovalPolicy
from agent.domain_packs.protein_design.telemetry import summarize_validation_metrics
from agent.domain_packs.protein_design.tools import _gpu_plan, _parse_hardware_errors


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_protein_design_tools_are_registered_for_llm():
    tools = create_builtin_tools(local_mode=True, domain_pack="protein_design")
    specs = {tool.name: tool for tool in tools}

    assert "run_pxdesign" in specs
    assert "run_boltzgen" in specs
    assert "run_bindcraft" in specs
    assert "protein_design_ace_playbook" in specs
    assert "target_pdb" in specs["run_pxdesign"].parameters["required"]


def test_default_binder_pack_still_omits_protein_design_tools():
    tools = create_builtin_tools(local_mode=True)
    specs = {tool.name: tool for tool in tools}

    assert "binder_design" in specs
    assert "run_pxdesign" not in specs


def test_protein_design_domain_pack_config_is_accepted(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "model_name": "moonshotai/Kimi-K2.6",
                "domain_pack": "protein_design",
            }
        ),
        encoding="utf-8",
    )

    config = config_module.load_config(str(config_path))

    assert config.domain_pack == "protein_design"


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
    assert await policy.decide("run_bindcraft", {"iterations": 101}, None)


def test_core_approval_policy_covers_protein_design_tools():
    assert agent_loop._needs_approval("run_pxdesign", {"num_samples": 250})
    assert agent_loop._needs_approval("run_boltzgen", {"num_samples": 250})
    assert agent_loop._needs_approval("run_bindcraft", {"iterations": 101})
    assert not agent_loop._needs_approval("run_bindcraft", {"iterations": 100})


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
