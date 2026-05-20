"""Compatibility namespace for legacy domain-specific modules."""

from __future__ import annotations

from typing import Any


def create_domain_tools(_workflow: str, _tool_spec_cls: type) -> list[Any]:
    """Deprecated compatibility shim.

    Domain-specific tools are registered as normal built-in tools now.
    """
    return []
