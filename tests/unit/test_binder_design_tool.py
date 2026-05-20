import json

import pytest

from agent.core.tools import create_builtin_tools
from agent.tools.binder_design_tool import binder_design_handler


@pytest.mark.asyncio
async def test_binder_design_create_project_writes_manifest(tmp_path):
    project_dir = tmp_path / "pd1_binders"

    text, ok = await binder_design_handler(
        {
            "operation": "create_project",
            "project_dir": str(project_dir),
            "target_name": "PD-1",
            "target_structure": "5IUS",
            "requirements": {"chain": "A", "binder_length": "80-140"},
            "tools": ["bindcraft", "pxdesign"],
        }
    )

    assert ok is True
    payload = json.loads(text)
    manifest = project_dir / "binder_project.json"
    assert payload["manifest"] == str(manifest)
    assert manifest.exists()
    data = json.loads(manifest.read_text())
    assert data["target_name"] == "PD-1"
    assert data["tools"] == ["bindcraft", "pxdesign"]
    assert data["campaign_plan"]["difficulty"] == "standard"
    assert "acceptance_criteria" in data["campaign_plan"]
    assert (project_dir / "outputs").is_dir()
    assert (project_dir / "skills").is_dir()


@pytest.mark.asyncio
async def test_binder_design_plans_hard_campaign():
    text, ok = await binder_design_handler(
        {
            "operation": "plan_campaign",
            "target_name": "PD-L1",
            "target_structure": "5J89",
            "strict_validation": True,
            "requirements": {
                "target_chains": ["A"],
                "epitope": "PD-1 interface",
                "hotspots": ["Y56", "M115"],
                "glycosylation": True,
                "membrane_context": True,
                "species_cross_reactivity": ["human", "mouse"],
                "binder_length": "70-130",
            },
        }
    )

    assert ok is True
    payload = json.loads(text)
    plan = payload["campaign_plan"]
    assert plan["difficulty"] == "hard"
    assert plan["acceptance_criteria"]["primary_filters"]["iptm"] == 0.8
    assert any(item["tool"] == "BoltzGen" for item in plan["tool_strategy"])
    assert any("glycan" in item["risk"] for item in plan["risk_register"])


@pytest.mark.asyncio
async def test_binder_design_ranks_candidates_from_csv(tmp_path):
    metrics = tmp_path / "final_design_stats.csv"
    metrics.write_text(
        "\n".join(
            [
                "Design,Average_pLDDT,Average_i_pAE,Interface_Score,Clashes,Sequence,Validation_Source,Fold_Cluster",
                "binder_a,92,3.5,-20,0,AAAA,Chai-1,cluster_1",
                "binder_b,70,2.0,-5,0,BBBB,Generator,cluster_1",
                "binder_c,95,9.0,-30,4,CCCC,Protenix,cluster_2",
            ]
        ),
        encoding="utf-8",
    )

    text, ok = await binder_design_handler(
        {
            "operation": "rank_candidates",
            "outputs_dir": str(tmp_path),
            "filters": {"plddt": 80, "ipae": 5, "clashes": 0},
            "top_k": 2,
        }
    )

    assert ok is True
    payload = json.loads(text)
    assert payload["candidate_count"] == 3
    assert payload["passed_count"] == 1
    assert payload["rejected_count"] == 2
    assert payload["top_candidates"][0]["name"] == "binder_a"
    assert payload["top_candidates"][0]["sequence"] == "AAAA"
    assert payload["top_candidates"][0]["decision"] == "advance"
    assert payload["top_candidates"][0]["validation_tier"] == "orthogonal"
    assert payload["diversity_representatives"][0]["fold_cluster"] == "cluster_1"


@pytest.mark.asyncio
async def test_binder_design_holds_generator_only_candidates_for_validation(tmp_path):
    metrics = tmp_path / "metrics.csv"
    metrics.write_text(
        "\n".join(
            [
                "Design,Average_pLDDT,Average_i_pAE,Clashes,Validation_Source",
                "binder_a,91,3.2,0,Generator",
            ]
        ),
        encoding="utf-8",
    )

    text, ok = await binder_design_handler(
        {
            "operation": "rank_candidates",
            "outputs_dir": str(tmp_path),
            "filters": {"plddt": 80, "ipae": 5, "clashes": 0},
        }
    )

    assert ok is True
    payload = json.loads(text)
    top = payload["top_candidates"][0]
    assert top["decision"] == "hold_for_orthogonal_validation"
    assert "run orthogonal Chai-1/Protenix validation" in top["next_actions"]


@pytest.mark.asyncio
async def test_binder_design_parses_bindcraft_metric_headers(tmp_path):
    metrics = tmp_path / "final_design_stats.csv"
    metrics.write_text(
        "\n".join(
            [
                (
                    "Design,Average_pLDDT,Average_i_pTM,Average_i_pAE,"
                    "Average_Relaxed_Clashes,Average_dG,Average_n_InterfaceResidues,"
                    "Average_n_InterfaceHbonds,Average_dSASA,Average_Binder_RMSD,"
                    "Sequence,Validation_Source,Fold_Cluster"
                ),
                "binder_a,91,0.82,3.4,0,-28,32,4,1400,1.8,AAAA,Chai-1,cluster_1",
            ]
        ),
        encoding="utf-8",
    )

    text, ok = await binder_design_handler(
        {
            "operation": "rank_candidates",
            "outputs_dir": str(tmp_path),
            "top_k": 1,
        }
    )

    assert ok is True
    payload = json.loads(text)
    top = payload["top_candidates"][0]
    assert top["iptm"] == 0.82
    assert top["clashes"] == 0
    assert top["interface_score"] == -28
    assert top["interface_contacts"] == 32
    assert top["interface_hbonds"] == 4
    assert top["buried_sasa"] == 1400
    assert top["rmsd"] == 1.8
    assert top["decision"] == "advance"


@pytest.mark.asyncio
async def test_binder_design_exports_reusable_skill_card(tmp_path):
    project_dir = tmp_path / "pd1_binders"
    await binder_design_handler(
        {
            "operation": "create_project",
            "project_dir": str(project_dir),
            "target_name": "PD-L1",
            "target_structure": "5J89",
            "requirements": {"target_chains": ["A"], "binder_length": "70-130"},
            "tools": ["bindcraft", "chai-1", "foldseek"],
        }
    )

    text, ok = await binder_design_handler(
        {
            "operation": "export_skill",
            "project_dir": str(project_dir),
            "skill_name": "pd1_binder_campaign",
        }
    )

    assert ok is True
    payload = json.loads(text)
    skill_path = project_dir / "skills" / "pd1_binder_campaign.md"
    assert payload["skill_name"] == "pd1_binder_campaign"
    assert payload["skill_path"] == str(skill_path)
    assert skill_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    assert "pd1_binder_campaign" in content
    assert "Reusable AIDD binder-design workflow" in content
    assert "PD-L1" in content
    assert "5J89" in content


@pytest.mark.asyncio
async def test_binder_design_end_to_end_file_backed_campaign(tmp_path):
    project_dir = tmp_path / "pd_l1_campaign"
    emitted_steps: list[str] = []

    def emit_step(payload: dict[str, object]) -> None:
        emitted_steps.append(str(payload["step"]))
        print(json.dumps(payload, sort_keys=True))

    plan_text, ok = await binder_design_handler(
        {
            "operation": "plan_campaign",
            "target_name": "PD-L1",
            "target_structure": "5J89",
            "strict_validation": True,
            "requirements": {
                "target_chains": ["A"],
                "epitope": "PD-1 interface",
                "hotspots": ["Y56", "M115"],
                "glycosylation": True,
                "membrane_context": True,
                "binder_length": "70-130",
            },
        }
    )
    assert ok is True
    plan = json.loads(plan_text)
    emit_step(
        {
            "step": "plan_campaign",
            "status": plan["status"],
            "difficulty": plan["campaign_plan"]["difficulty"],
            "primary_filters": plan["campaign_plan"]["acceptance_criteria"][
                "primary_filters"
            ],
        }
    )

    create_text, ok = await binder_design_handler(
        {
            "operation": "create_project",
            "project_dir": str(project_dir),
            "target_name": "PD-L1",
            "target_structure": "5J89",
            "strict_validation": True,
            "requirements": {
                "target_chains": ["A"],
                "epitope": "PD-1 interface",
                "binder_length": "70-130",
            },
            "tools": ["bindcraft", "chai-1", "foldseek"],
        }
    )
    assert ok is True
    created = json.loads(create_text)
    manifest_path = project_dir / "binder_project.json"
    assert created["manifest"] == str(manifest_path)
    assert manifest_path.exists()
    emit_step(
        {
            "step": "create_project",
            "status": created["status"],
            "manifest_exists": manifest_path.exists(),
        }
    )

    outputs_dir = project_dir / "outputs" / "bindcraft_run_001"
    outputs_dir.mkdir(parents=True)
    metrics_path = outputs_dir / "final_design_stats.csv"
    metrics_path.write_text(
        "\n".join(
            [
                (
                    "Design,Average_pLDDT,Average_i_pTM,Average_i_pAE,"
                    "Average_Relaxed_Clashes,Average_dG,Average_n_InterfaceResidues,"
                    "Average_n_InterfaceHbonds,Average_dSASA,Average_Binder_RMSD,"
                    "Sequence,Validation_Source,Fold_Cluster"
                ),
                "pdl1_binder_a,92,0.84,3.1,0,-31,34,5,1550,1.6,ACDEFGHIK,Chai-1,cluster_a",
                "pdl1_binder_b,88,0.78,4.4,0,-24,29,3,1290,2.2,LMNPQRSTV,Protenix,cluster_b",
                "pdl1_binder_c,73,0.71,6.8,1,-11,18,1,760,4.9,WYACDEFGH,Generator,cluster_c",
            ]
        ),
        encoding="utf-8",
    )

    inspect_text, ok = await binder_design_handler(
        {"operation": "inspect_outputs", "outputs_dir": str(project_dir / "outputs")}
    )
    assert ok is True
    inspected = json.loads(inspect_text)
    assert inspected["candidate_count"] == 3
    assert str(metrics_path) in inspected["metric_files"]
    emit_step(
        {
            "step": "inspect_outputs",
            "status": inspected["status"],
            "candidate_count": inspected["candidate_count"],
            "metric_files": inspected["metric_files"],
        }
    )

    rank_text, ok = await binder_design_handler(
        {
            "operation": "rank_candidates",
            "outputs_dir": str(project_dir / "outputs"),
            "filters": {"plddt": 80, "iptm": 0.75, "ipae": 5, "clashes": 0},
            "top_k": 5,
        }
    )
    assert ok is True
    ranked = json.loads(rank_text)
    assert ranked["candidate_count"] == 3
    assert ranked["passed_count"] == 2
    assert ranked["rejected_count"] == 1
    assert [item["name"] for item in ranked["top_candidates"]] == [
        "pdl1_binder_a",
        "pdl1_binder_b",
    ]
    assert ranked["top_candidates"][0]["decision"] == "advance"
    assert len(ranked["diversity_representatives"]) == 2
    emit_step(
        {
            "step": "rank_candidates",
            "status": ranked["status"],
            "passed_count": ranked["passed_count"],
            "rejected_count": ranked["rejected_count"],
            "top_candidates": [item["name"] for item in ranked["top_candidates"]],
        }
    )

    skill_text, ok = await binder_design_handler(
        {
            "operation": "export_skill",
            "project_dir": str(project_dir),
            "skill_name": "pd_l1_binder_design",
        }
    )
    assert ok is True
    skill = json.loads(skill_text)
    skill_path = project_dir / "skills" / "pd_l1_binder_design.md"
    assert skill["skill_path"] == str(skill_path)
    assert skill_path.exists()
    assert "Reusable AIDD binder-design workflow" in skill_path.read_text(
        encoding="utf-8"
    )
    emit_step(
        {
            "step": "export_skill",
            "status": skill["status"],
            "skill_path": skill["skill_path"],
        }
    )

    assert emitted_steps == [
        "plan_campaign",
        "create_project",
        "inspect_outputs",
        "rank_candidates",
        "export_skill",
    ]


def test_binder_design_is_registered_for_llm():
    tools = create_builtin_tools(local_mode=True)
    specs = {tool.name: tool for tool in tools}

    assert "binder_design" in specs
    assert (
        "rank_candidates"
        in specs["binder_design"].parameters["properties"]["operation"]["enum"]
    )
    assert (
        "plan_campaign"
        in specs["binder_design"].parameters["properties"]["operation"]["enum"]
    )
    assert (
        "export_skill"
        in specs["binder_design"].parameters["properties"]["operation"]["enum"]
    )
    assert "skill_name" in specs["binder_design"].parameters["properties"]

