"""
Memory Engine optimized for AIDD-Intern AI Agents.
Integrates the dual-memory architecture inspired by the TencentDB-Agent-Memory framework:
1. Symbolic Short-Term Memory (via Mermaid Task Canvas) to offload heavy tool execution traces.
2. Layered Long-Term Memory (4-Tier Pipeline) mapping semantic MemU client records into structured levels (L0, L1, L2, L3).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Union
from agent.core.memu import MemUClient

logger = logging.getLogger(__name__)


class MermaidTaskCanvas:
    """
    Symbolic Short-Term Memory (inspired by the TencentDB-Agent-Memory framework).
    Models the progress of complex tasks as a compact, visual Mermaid diagram
    to save context window tokens and improve task execution visibility.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[tuple[str, str]] = []

    def add_node(
        self, name: str, status: str = "PENDING", details: str | None = None
    ) -> None:
        """Add or update a node on the canvas."""
        self.nodes[name] = {
            "status": status,
            "details": details or "",
        }

    def update_node(self, name: str, status: str, details: str | None = None) -> None:
        """Update the status of an existing node or add it if not present."""
        if name not in self.nodes:
            self.add_node(name, status, details)
        else:
            self.nodes[name]["status"] = status
            if details is not None:
                self.nodes[name]["details"] = details

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add an edge between two nodes if it doesn't already exist."""
        edge = (from_node, to_node)
        if edge not in self.edges:
            self.edges.append(edge)

    def clear(self) -> None:
        """Clear all nodes and edges."""
        self.nodes.clear()
        self.edges.clear()

    def render_mermaid(self) -> str:
        """Renders the flowchart in beautiful, valid Mermaid syntax."""
        if not self.nodes:
            return "```mermaid\ngraph TD\n    Empty[No task initialized]\n```"

        lines = ["graph TD"]

        # Helper to format node labels
        def escape_label(label: str) -> str:
            return label.replace('"', '\\"')

        # Output nodes with TencentDB-Agent-Memory visual state styles
        for node_id, info in self.nodes.items():
            status = info["status"]
            details = info["details"]
            label = node_id
            if details:
                label = f"{node_id} ({details})"

            # Format shape based on status
            if status == "SUCCESS":
                lines.append(f'    {node_id}["🟢 {escape_label(label)}"]')
                lines.append(
                    f"    style {node_id} fill:#E8F5E9,stroke:#4CAF50,stroke-width:2px,color:#2E7D32"
                )
            elif status == "FAILED":
                lines.append(f'    {node_id}["🔴 {escape_label(label)}"]')
                lines.append(
                    f"    style {node_id} fill:#FFEBEE,stroke:#EF5350,stroke-width:2px,color:#C62828"
                )
            elif status == "RUNNING":
                lines.append(f'    {node_id}["🔵 {escape_label(label)}"]')
                lines.append(
                    f"    style {node_id} fill:#E3F2FD,stroke:#2196F3,stroke-width:2px,color:#1565C0"
                )
            else:  # PENDING or other
                lines.append(f'    {node_id}["🟡 {escape_label(label)}"]')
                lines.append(
                    f"    style {node_id} fill:#FFFDE7,stroke:#FBC02D,stroke-width:2px,color:#F57F17"
                )

        # Output edges
        for from_node, to_node in self.edges:
            # Ensure referenced nodes exist on the canvas
            if from_node not in self.nodes:
                self.add_node(from_node, "PENDING")
            if to_node not in self.nodes:
                self.add_node(to_node, "PENDING")
            lines.append(f"    {from_node} --> {to_node}")

        return "```mermaid\n" + "\n".join(lines) + "\n```"


class LayeredMemoryPipeline:
    """
    Layered Long-Term Memory Pipeline (inspired by the TencentDB-Agent-Memory framework).
    Structures long-term memories retrieved via MemU into 4 layers:
      - L0: Raw dialogues (verbatim record of interactions)
      - L1: Atomic memory (individual facts, preferences, constraints)
      - L2: Scenario Blocks (task-specific structured category summaries in Markdown)
      - L3: User Profile (consolidated user profile/persona in Markdown)
    """

    def __init__(self, client: MemUClient | None = None) -> None:
        self.client = client or MemUClient()

    def format_layered_memories(
        self,
        retrieval_res: Dict[str, Any],
        user_name: str | None = None,
    ) -> Dict[str, Any]:
        """
        Structures the raw MemU retrieval response into the 4-tier pipeline format:
        - L1_atomic: Facts, preferences, constraints extracted from items.
        - L2_scenarios: Categorized Markdown summary sections.
        - L3_profile: Consolidated User profile.
        """
        user_label = user_name or "User"

        # 1. Extract L1 (Atomic Memory) from retrieve items
        l1_items = retrieval_res.get("items") or []
        l1_atomic = []
        for item in l1_items:
            mtype = item.get("memory_type", "fact")
            content = item.get("content", "")
            if content:
                l1_atomic.append({"type": mtype, "content": content})

        # 2. Extract L2 (Scenario Blocks) from retrieve categories
        l2_categories = retrieval_res.get("categories") or []
        l2_scenarios = {}
        for cat in l2_categories:
            name = cat.get("name", "general")
            desc = cat.get("description", "")
            summary = cat.get("summary", "")
            l2_scenarios[name] = {"description": desc, "summary": summary}

        # 3. Construct L3 (User Profile) by combining atomic preferences and scenario summaries
        l3_lines = [f"# {user_label} Profile & Persona"]

        # Prefs
        prefs = [
            it["content"] for it in l1_atomic if it["type"] in ("preference", "habit")
        ]
        if prefs:
            l3_lines.append("## Personal Preferences & Habits")
            for pref in prefs:
                l3_lines.append(f"- {pref}")
        else:
            l3_lines.append(
                "## Personal Preferences & Habits\n*(No recorded preferences)*"
            )

        # Constraints
        constraints = [it["content"] for it in l1_atomic if it["type"] == "constraint"]
        if constraints:
            l3_lines.append("## Operational Constraints")
            for const in constraints:
                l3_lines.append(f"- {const}")

        # Summaries of categories
        if l2_scenarios:
            l3_lines.append("## Scenario Summaries")
            for name, details in l2_scenarios.items():
                l3_lines.append(f"### Category: {name}")
                l3_lines.append(details["summary"])

        l3_profile = "\n".join(l3_lines)

        # 4. Render the beautiful, structured 4-tier prompt block
        prompt_blocks = [
            "==================================================",
            "🧠 LAYERED LONG-TERM MEMORY ENGINE (TencentDB-Agent-Memory Schema)",
            "==================================================",
        ]

        prompt_blocks.append("\n[L3: USER PROFILE & PERSONA]")
        prompt_blocks.append(l3_profile)

        prompt_blocks.append("\n[L2: ACTIVE SCENARIO BLOCKS]")
        if l2_scenarios:
            for name, details in l2_scenarios.items():
                prompt_blocks.append(f"### Scenario [{name}]: {details['description']}")
                prompt_blocks.append(details["summary"])
        else:
            prompt_blocks.append("*(No active scenario blocks)*")

        prompt_blocks.append("\n[L1: ATOMIC FACTS & PREFERENCES]")
        if l1_atomic:
            for i, it in enumerate(l1_atomic, 1):
                prompt_blocks.append(f"{i}. [{it['type'].upper()}] {it['content']}")
        else:
            prompt_blocks.append("*(No atomic memories retrieved)*")

        prompt_blocks.append("==================================================")
        formatted_prompt = "\n".join(prompt_blocks)

        return {
            "L1_atomic": l1_atomic,
            "L2_scenarios": l2_scenarios,
            "L3_profile": l3_profile,
            "formatted_prompt": formatted_prompt,
        }

    def retrieve_layered(
        self,
        user_id: str,
        agent_id: str,
        query: Union[str, List[Dict[str, Any]]],
        user_name: str | None = None,
    ) -> Dict[str, Any]:
        """
        Performs semantic retrieval from MemU and returns structured hierarchical layers.
        """
        raw_res = self.client.retrieve(user_id=user_id, agent_id=agent_id, query=query)
        structured = self.format_layered_memories(raw_res, user_name=user_name)
        # Include original fields for maximum backwards compatibility
        return {**raw_res, **structured}
