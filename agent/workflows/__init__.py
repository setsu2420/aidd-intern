"""Domain-pack registry for AIDD-Intern.

The runtime stays generic; domain packs add domain-specific tools and workflow
policy in one place.
"""

from __future__ import annotations

from typing import Any


DEFAULT_DOMAIN_PACK = "aidd_binder"
SUPPORTED_DOMAIN_PACKS = {"aidd_binder", "none", "protein_design"}


def create_domain_tools(domain_pack: str, tool_spec_cls: type) -> list[Any]:
    """Return tool specs contributed by the selected domain pack."""
    if domain_pack == "none":
        return []
    if domain_pack == "aidd_binder":
        from agent.domain_packs.aidd_binder.tools import create_tools

        return create_tools(tool_spec_cls)
    if domain_pack == "protein_design":
        from agent.domain_packs.protein_design.tools import create_protein_design_tools

        return create_protein_design_tools(tool_spec_cls)
    raise ValueError(
        f"Unsupported domain_pack={domain_pack!r}. "
        f"Supported values: {', '.join(sorted(SUPPORTED_DOMAIN_PACKS))}"
    )
