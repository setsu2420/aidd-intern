"""
Reflector — ACE-inspired structured reflection engine.

Analyses completed binder-design sessions using an LLM to extract deep
insights that simple regex-based extraction (SkillExtractor) would miss.

Architecture (ACE Generator-Reflector-Curator):
  Generator  → SkillExtractor extracts raw patterns (regex + heuristics)
  Reflector  → LLM-driven deep analysis of session trajectories
  Curator    → KnowledgeWiki.ingest_reflector_report() applies deltas

The Reflector produces a ``ReflectionReport`` with:
  • Key insights (what worked, what failed, surprising findings)
  • Strategy updates (param refinements, new lessons for existing entries)
  • New strategies (entirely new approaches discovered)
  • Anti-patterns (what to avoid, with recommendations)
  • Effectiveness assessment (which strategies to promote/demote)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ReflectorInsight:
    """A single insight extracted by the Reflector."""

    content: str
    category: str  # "success" | "failure" | "surprise" | "optimization"
    target: str | None = None
    title: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "category": self.category,
            "target": self.target,
            "title": self.title or self.content[:60],
            "confidence": self.confidence,
        }


@dataclass
class ReflectionReport:
    """Structured output of the Reflector analysis."""

    session_id: str | None = None
    insights: list[dict[str, Any]] = field(default_factory=list)
    strategy_updates: list[dict[str, Any]] = field(default_factory=list)
    new_strategies: list[dict[str, Any]] = field(default_factory=list)
    anti_patterns: list[dict[str, Any]] = field(default_factory=list)
    effectiveness_assessment: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "insights": self.insights,
            "strategy_updates": self.strategy_updates,
            "new_strategies": self.new_strategies,
            "anti_patterns": self.anti_patterns,
            "effectiveness_assessment": self.effectiveness_assessment,
            "summary": self.summary,
        }

    @property
    def is_empty(self) -> bool:
        return (
            not self.insights
            and not self.strategy_updates
            and not self.new_strategies
            and not self.anti_patterns
        )


# ---------------------------------------------------------------------------
# Reflector prompt template
# ---------------------------------------------------------------------------

_REFLECTOR_SYSTEM_PROMPT = """\
You are the **Reflector** in an Agentic Context Engineering (ACE) pipeline.

Your task is to deeply analyse a completed binder-design session and extract
structured insights that go beyond surface-level pattern matching.

Focus on:
1. **Key Insights**: What actually worked? What failed? Any surprising findings?
2. **Strategy Updates**: Should existing strategies be refined (params, lessons)?
3. **New Strategies**: Were entirely new approaches discovered?
4. **Anti-Patterns**: What should future sessions actively avoid?
5. **Effectiveness**: Which historical strategies proved helpful vs harmful?

Output MUST be valid JSON with this exact schema:
```json
{
  "summary": "1-2 sentence session summary",
  "insights": [
    {
      "content": "detailed insight description (min 20 chars)",
      "category": "success|failure|surprise|optimization",
      "target": "target protein name or null",
      "title": "short title",
      "confidence": 0.0-1.0
    }
  ],
  "strategy_updates": [
    {
      "entry_id": "wiki-xxxxxxxxxx (if known, else empty)",
      "match_title": "title to match existing entry",
      "add_lessons": ["new lesson to add"],
      "update_params": {"key": "new_value"}
    }
  ],
  "new_strategies": [
    {
      "title": "strategy title",
      "target": "target name or null",
      "tool_chain": ["tool1", "tool2"],
      "params": {"key": "value"},
      "lessons": ["lesson 1", "lesson 2"]
    }
  ],
  "anti_patterns": [
    {
      "description": "what to avoid",
      "target": "target or null",
      "recommendation": "what to do instead"
    }
  ],
  "effectiveness_assessment": [
    {
      "match_title": "existing entry title",
      "verdict": "helpful|harmful|neutral",
      "reason": "why"
    }
  ]
}
```

Be specific and detailed. Avoid vague generalities. Each insight should be
actionable and self-contained (a reader should understand it without context).
"""


# ---------------------------------------------------------------------------
# Reflector engine
# ---------------------------------------------------------------------------


class Reflector:
    """
    ACE Reflector: LLM-driven session analysis.

    Uses an LLM to perform deep reflection on a completed session,
    producing a structured ``ReflectionReport`` for the Curator
    (KnowledgeWiki) to ingest as incremental deltas.

    Parameters
    ----------
    llm_model:
        Model identifier for the reflection LLM.
        Defaults to the project default model.
    """

    def __init__(self, llm_model: str | None = None) -> None:
        self._model = llm_model

    async def reflect(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        session_id: str | None = None,
        existing_entries: list[Any] | None = None,
    ) -> ReflectionReport:
        """
        Analyse a session's message history and produce a ReflectionReport.

        Parameters
        ----------
        messages:
            Session conversation messages.
        session_id:
            Optional session identifier.
        existing_entries:
            Optional list of current KnowledgeEntry objects to help the
            Reflector produce targeted strategy_updates.

        Returns a ``ReflectionReport``. On failure, returns an empty report.
        """
        if len(messages) < 6:
            logger.debug("Session too short for reflection (%d msgs)", len(messages))
            return ReflectionReport(session_id=session_id)

        # Build the session digest
        digest = self._build_session_digest(messages)

        # Build existing knowledge context (brief)
        knowledge_ctx = ""
        if existing_entries:
            knowledge_ctx = self._build_knowledge_context(existing_entries)

        # Call LLM
        try:
            report = await self._call_llm(digest, knowledge_ctx, session_id)
            return report
        except Exception as exc:
            logger.warning("Reflector LLM call failed (non-fatal): %s", exc)
            return ReflectionReport(session_id=session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_session_digest(self, messages: Sequence[dict[str, Any]]) -> str:
        """Create a compact but information-rich session summary for the LLM."""
        lines: list[str] = []
        msg_count = len(messages)
        lines.append(f"Session: {msg_count} messages")
        lines.append("")

        # Include key messages (first, last, tool calls, metric results)
        included_indices: set[int] = set()

        # First 3 messages (context setting)
        for i in range(min(3, msg_count)):
            included_indices.add(i)

        # Last 5 messages (outcomes)
        for i in range(max(0, msg_count - 5), msg_count):
            included_indices.add(i)

        # Tool calls and results
        for i, msg in enumerate(messages):
            content = str(msg.get("content", ""))
            role = msg.get("role", "")
            # Tool invocations
            if role == "assistant" and any(
                kw in content.lower()
                for kw in ["run_bindcraft", "run_pxdesign", "run_boltzgen", "run_rfd3"]
            ):
                included_indices.add(i)
            # Metric results
            if any(
                kw in content.lower()
                for kw in ["iptm", "plddt", "pae", "clashes", "success rate"]
            ):
                included_indices.add(i)
            # Errors
            if any(kw in content.lower() for kw in ["error", "failed", "oom", "cuda"]):
                included_indices.add(i)

        for i in sorted(included_indices):
            msg = messages[i]
            role = msg.get("role", "unknown")
            content = str(msg.get("content", ""))
            # Truncate very long messages
            if len(content) > 800:
                content = content[:800] + "... (truncated)"
            lines.append(f"[{i}] {role}: {content}")
            lines.append("")

        return "\n".join(lines)

    def _build_knowledge_context(self, entries: list[Any]) -> str:
        """Build a brief context of existing wiki entries for the Reflector."""
        lines: list[str] = ["Existing Knowledge Entries:"]
        for entry in entries[:10]:
            title = getattr(entry, "title", "unknown")
            target = getattr(entry, "target", None) or ""
            entry_id = getattr(entry, "id", "")
            version = getattr(entry, "version", 1)
            helpful = getattr(entry, "helpful_count", 0)
            harmful = getattr(entry, "harmful_count", 0)
            lines.append(
                f"  - [{entry_id}] {title} (target={target}, v{version}, "
                f"↗{helpful}/↘{harmful})"
            )
        return "\n".join(lines)

    async def _call_llm(
        self,
        digest: str,
        knowledge_ctx: str,
        session_id: str | None,
    ) -> ReflectionReport:
        """Call the LLM with the reflection prompt and parse the response."""
        from litellm import acompletion

        user_prompt_parts = [
            "Analyse this completed binder-design session and extract structured insights.",
            "",
            "## Session Digest",
            digest,
        ]
        if knowledge_ctx:
            user_prompt_parts.extend(["", "## Existing Knowledge", knowledge_ctx])

        user_prompt = "\n".join(user_prompt_parts)

        # Use a lightweight, fast model for reflection
        model = self._model or "anthropic/claude-sonnet-4-20250514"

        response = await acompletion(
            model=model,
            messages=[
                {"role": "system", "content": _REFLECTOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2000,
            temperature=0.3,
        )

        # Extract text from litellm response
        text = response.choices[0].message.content if response.choices else ""
        return self._parse_report(text or "", session_id)

    def _parse_report(self, text: str, session_id: str | None) -> ReflectionReport:
        """Parse LLM output into a ReflectionReport."""
        # Try to find JSON block in the response
        json_str = self._extract_json(text)
        if not json_str:
            logger.warning("Reflector: no JSON found in LLM response")
            return ReflectionReport(session_id=session_id, summary=text[:200])

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.warning("Reflector: JSON parse error: %s", exc)
            return ReflectionReport(session_id=session_id, summary=text[:200])

        return ReflectionReport(
            session_id=session_id,
            insights=data.get("insights", []),
            strategy_updates=data.get("strategy_updates", []),
            new_strategies=data.get("new_strategies", []),
            anti_patterns=data.get("anti_patterns", []),
            effectiveness_assessment=data.get("effectiveness_assessment", []),
            summary=data.get("summary", ""),
        )

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """Extract the first JSON object/block from text."""
        # Try fenced code block first
        import re

        fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        # Try raw JSON
        brace_depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == "{":
                if start == -1:
                    start = i
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if brace_depth == 0 and start >= 0:
                    return text[start : i + 1]
        return None
