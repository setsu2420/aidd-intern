"""Tool for creating structured multi-agent role handoff packages."""

from __future__ import annotations

import json
from typing import Any

from agent.roles import create_handoff, list_roles


ROLE_HANDOFF_TOOL_SPEC = {
    "name": "role_handoff",
    "description": (
        "Create structured handoff packages between AIDD-Intern specialist roles. "
        "Use before delegating work or when handing artifacts from one role to another."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list_roles", "create_handoff"],
            },
            "source_role": {"type": "string"},
            "target_role": {"type": "string"},
            "task_intent": {"type": "string"},
            "constraints": {"type": "array", "items": {"type": "string"}},
            "artifacts": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "array", "items": {"type": "object"}},
            "open_questions": {"type": "array", "items": {"type": "string"}},
            "budget": {"type": "object"},
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "default": "medium",
            },
        },
        "required": ["operation"],
    },
}


def _format(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


async def role_handoff_handler(arguments: dict[str, Any]) -> tuple[str, bool]:
    try:
        operation = arguments.get("operation")
        if operation == "list_roles":
            return _format([role.__dict__ for role in list_roles()]), True
        if operation == "create_handoff":
            handoff = create_handoff(
                source_role=arguments["source_role"],
                target_role=arguments["target_role"],
                task_intent=arguments["task_intent"],
                constraints=arguments.get("constraints"),
                artifacts=arguments.get("artifacts"),
                evidence=arguments.get("evidence"),
                open_questions=arguments.get("open_questions"),
                budget=arguments.get("budget"),
                risk_level=arguments.get("risk_level") or "medium",
            )
            return handoff.to_json(), True
        return _format({"status": "error", "message": "Unknown operation."}), False
    except Exception as exc:
        return _format({"status": "error", "message": str(exc)}), False
