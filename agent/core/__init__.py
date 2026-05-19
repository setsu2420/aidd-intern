"""
Core agent implementation
Contains the main agent logic, decision-making, and orchestration
"""

__all__ = ["ToolRouter", "ToolSpec", "create_builtin_tools"]


def __getattr__(name: str):
    if name in __all__:
        from agent.core.tools import ToolRouter, ToolSpec, create_builtin_tools

        return {
            "ToolRouter": ToolRouter,
            "ToolSpec": ToolSpec,
            "create_builtin_tools": create_builtin_tools,
        }[name]
    raise AttributeError(f"module 'agent.core' has no attribute {name!r}")
