"""Tool registration for the AIDD Binder domain pack."""

from __future__ import annotations

from typing import Any

from agent.tools.binder_design_tool import (
    BINDER_DESIGN_TOOL_SPEC,
    binder_design_handler,
)


def create_tools(tool_spec_cls: type) -> list[Any]:
    """Create ToolSpec instances for Binder-design workflows."""
    return [
        tool_spec_cls(
            name=BINDER_DESIGN_TOOL_SPEC["name"],
            description=BINDER_DESIGN_TOOL_SPEC["description"],
            parameters=BINDER_DESIGN_TOOL_SPEC["parameters"],
            handler=binder_design_handler,
        )
    ]
