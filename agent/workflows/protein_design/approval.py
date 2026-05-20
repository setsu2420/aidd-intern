"""Approval boundaries for high-cost protein-design execution."""

from __future__ import annotations

from typing import Any


class ProteinDesignApprovalPolicy:
    """Compute and hardware safety policy for protein-design tools."""

    async def decide(self, tool_name: str, args: dict[str, Any], session: Any) -> bool:
        """Return True when the call must pause for human authorization."""
        if tool_name in {"run_pxdesign", "run_boltzgen"}:
            if int(args.get("num_samples") or 0) > 200:
                return True
        if tool_name == "run_bindcraft":
            if int(args.get("iterations") or 0) > 100:
                return True
        return False
