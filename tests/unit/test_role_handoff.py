import json

import pytest

from agent.core.tools import create_builtin_tools
from agent.roles import create_handoff, get_role
from agent.tools.role_handoff_tool import role_handoff_handler


def test_builtin_role_handoff_tool_is_registered():
    tools = create_builtin_tools(local_mode=True)
    specs = {tool.name: tool for tool in tools}

    assert "role_handoff" in specs
    assert (
        "create_handoff"
        in specs["role_handoff"].parameters["properties"]["operation"]["enum"]
    )


def test_create_handoff_includes_target_permissions():
    handoff = create_handoff(
        source_role="supervisor",
        target_role="executor",
        task_intent="Run approved PXdesign batch and capture manifest.",
        artifacts=["target_bundle.json"],
        constraints=["do not exceed GPU approval budget"],
    )

    assert handoff.source_role == "supervisor"
    assert handoff.target_role == "executor"
    assert handoff.permissions["can_run_gpu"] is True
    assert "run_pxdesign" in handoff.permissions["allowed_tools"]


@pytest.mark.asyncio
async def test_role_handoff_tool_lists_and_creates_packages():
    text, ok = await role_handoff_handler({"operation": "list_roles"})
    roles = json.loads(text)

    assert ok is True
    assert any(role["name"] == "supervisor" for role in roles)

    text, ok = await role_handoff_handler(
        {
            "operation": "create_handoff",
            "source_role": "supervisor",
            "target_role": "verifier",
            "task_intent": "Check candidate metrics for reward hacking.",
            "evidence": [{"source": "validation_metrics.json"}],
            "risk_level": "high",
        }
    )
    package = json.loads(text)

    assert ok is True
    assert package["target_role"] == "verifier"
    assert package["risk_level"] == "high"
    assert package["permissions"]["requires_verification"] is False


def test_protein_design_roles_are_registered_by_domain_import():
    import agent.domain_packs.protein_design  # noqa: F401

    role = get_role("structural_biologist")

    assert "aidd_bio" in role.allowed_tools
    assert role.output_contract == "structural_design_memo"
