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
    assert (project_dir / "outputs").is_dir()


@pytest.mark.asyncio
async def test_binder_design_ranks_candidates_from_csv(tmp_path):
    metrics = tmp_path / "final_design_stats.csv"
    metrics.write_text(
        "\n".join(
            [
                "Design,Average_pLDDT,Average_i_pAE,Interface_Score,Clashes,Sequence",
                "binder_a,92,3.5,-20,0,AAAA",
                "binder_b,70,2.0,-5,0,BBBB",
                "binder_c,95,9.0,-30,4,CCCC",
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


def test_binder_design_is_registered_for_llm():
    tools = create_builtin_tools(local_mode=True)
    specs = {tool.name: tool for tool in tools}

    assert "binder_design" in specs
    assert (
        "rank_candidates"
        in specs["binder_design"].parameters["properties"]["operation"]["enum"]
    )


def test_binder_design_is_omitted_without_domain_pack():
    tools = create_builtin_tools(local_mode=True, domain_pack="none")
    specs = {tool.name: tool for tool in tools}

    assert "binder_design" not in specs
