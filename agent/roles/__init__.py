"""Role registry for multi-agent harness orchestration."""

from agent.roles.registry import (
    HandoffPackage,
    RoleSpec,
    create_handoff,
    get_role,
    list_roles,
    register_roles,
)

__all__ = [
    "HandoffPackage",
    "RoleSpec",
    "create_handoff",
    "get_role",
    "list_roles",
    "register_roles",
]
