"""
Skill Extractor — Self-Evolution Engine for Binder Design (Hermes-inspired).

Observes completed binder-design sessions and automatically extracts reusable
Skill files (Markdown, agentskills.io-compatible) that capture:
  • Successful hyperparameter combinations
  • Tool-orchestration strategies
  • Failure modes and recovery patterns
  • Target-specific lessons

Skills are stored in agent/skills/ and loaded as procedural memory on future runs.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

try:
    from aidd_intern_core import (
        is_binder_design_session_rust as _rust_is_binder,
        search_skills_rust as _rust_search_skills,
    )

    _RUST_AVAILABLE = True
except ImportError:
    _rust_is_binder = None
    _rust_search_skills = None
    _RUST_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Regex patterns for recognising tool calls in conversation messages
_TOOL_CALL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("run_bindcraft", re.compile(r"run_bindcraft", re.I)),
    ("run_pxdesign", re.compile(r"run_pxdesign", re.I)),
    ("run_boltzgen", re.compile(r"run_boltzgen", re.I)),
    ("run_rfd3", re.compile(r"run_rfd3|run_rfd", re.I)),
    ("run_chai1", re.compile(r"run_chai1", re.I)),
    ("run_protenix", re.compile(r"run_protenix", re.I)),
    ("run_proteinmpnn", re.compile(r"run_proteinmpnn|proteinmpnn", re.I)),
    ("run_esmfold", re.compile(r"run_esmfold|esmfold", re.I)),
    ("run_foldseek", re.compile(r"run_foldseek|foldseek", re.I)),
]

# Known hyperparameter keys (JSON-like) in assistant messages
_HYPERPARAM_KEYS = {
    "num_samples",
    "binder_length",
    "iterations",
    "temperature",
    "num_sequences",
    "num_recycles",
    "num_designs",
    "max_trajectories",
    "interface_residues",
    "hotspot_residues",
    "target_chains",
    "similarity_threshold",
    "device",
    "timeout_s",
}

# Metric patterns
_METRIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ipTM", re.compile(r"ipTM[:\s=]+([0-9.]+)", re.I)),
    ("pLDDT", re.compile(r"pLDDT[:\s=]+([0-9.]+)", re.I)),
    ("pAE", re.compile(r"pAE[:\s=]+([0-9.]+)", re.I)),
    ("clashes", re.compile(r"clashes[:\s=]+(\d+)", re.I)),
    ("rmsd", re.compile(r"rmsd[:\s=]+([0-9.]+)", re.I)),
    ("affinity_nM", re.compile(r"affinity[:\s=]+([0-9.]+)\s*nM", re.I)),
    ("success_rate", re.compile(r"success\s*rate[:\s=]+([0-9.]+%?)", re.I)),
]

_OOM_RE = re.compile(r"(cuda out of memory|out-of-memory|oom|cublas|cudnn)", re.I)
_RECOVERY_RE = re.compile(
    r"(reduced?\s+(num_samples|batch)|enabled?\s+mixed.?precision|"
    r"lowered?\s+temperature|halved|retried)",
    re.I,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SkillEntry:
    """A single extracted skill (procedural memory unit)."""

    title: str
    trigger: str
    target: str | None = None
    tool_chain: list[str] = field(default_factory=list)
    hyperparams: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, str] = field(default_factory=dict)
    lessons: list[str] = field(default_factory=list)
    failure_recovery: list[str] = field(default_factory=list)
    raw_snippets: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def skill_id(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        h = hashlib.md5(self.title.encode()).hexdigest()[:6]
        return f"skill-{slug}-{h}"

    def to_markdown(self) -> str:
        """Render the skill as a Markdown file (agentskills.io compatible)."""
        lines: list[str] = []
        lines.append(f"# {self.title}\n")

        # Trigger
        lines.append("## Trigger\n")
        lines.append(f"{self.trigger}\n")

        # Metadata
        lines.append("## Metadata\n")
        if self.target:
            lines.append(f"- **Target:** {self.target}")
        if self.tool_chain:
            lines.append(f"- **Tool Chain:** {' → '.join(self.tool_chain)}")
        if self.hyperparams:
            params_str = ", ".join(f"{k}={v}" for k, v in self.hyperparams.items())
            lines.append(f"- **Hyperparameters:** {params_str}")
        if self.metrics:
            metrics_str = ", ".join(f"{k}={v}" for k, v in self.metrics.items())
            lines.append(f"- **Outcome Metrics:** {metrics_str}")
        lines.append(f"- **Created:** {self.created_at}\n")

        # Steps (derived from tool chain + lessons)
        lines.append("## Steps\n")
        for i, tool in enumerate(self.tool_chain, 1):
            lines.append(f"{i}. Run `{tool}` with appropriate parameters")
        lines.append("")

        # Lessons learned
        if self.lessons:
            lines.append("## Lessons Learned\n")
            for lesson in self.lessons:
                lines.append(f"- {lesson}")
            lines.append("")

        # Failure recovery
        if self.failure_recovery:
            lines.append("## Failure Recovery\n")
            for recovery in self.failure_recovery:
                lines.append(f"- {recovery}")
            lines.append("")

        # Evidence snippets
        if self.raw_snippets:
            lines.append("## Evidence\n")
            for snippet in self.raw_snippets[:5]:
                lines.append(f"> {snippet[:300]}")
                lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core extractor
# ---------------------------------------------------------------------------


class SkillExtractor:
    """
    Observe → Plan → Act → Learn  (Hermes self-evolution loop).

    Analyses a completed binder-design conversation and extracts structured
    Skill files that encode successful strategies as procedural memory.
    """

    def __init__(self, skills_dir: Path | None = None) -> None:
        self.skills_dir = skills_dir or SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_from_session(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        session_id: str | None = None,
    ) -> list[SkillEntry]:
        """
        Analyse a session's message history and return extracted skills.

        Parameters
        ----------
        messages:
            List of ``{"role": "user"|"assistant"|"tool", "content": "..."}``
            dicts representing the conversation.
        session_id:
            Optional identifier for deduplication.
        """
        if len(messages) < 4:
            logger.debug("Session too short to extract skills (%d msgs)", len(messages))
            return []

        # 1. Detect if this is a binder design session
        if not self._is_binder_design_session(messages):
            return []

        # 2. Extract structured data
        target = self._extract_target(messages)
        tool_chain = self._extract_tool_chain(messages)
        hyperparams = self._extract_hyperparams(messages)
        metrics = self._extract_metrics(messages)
        lessons = self._extract_lessons(messages)
        failure_recovery = self._extract_failure_recovery(messages)

        if not tool_chain:
            logger.debug("No tool chain detected; skipping skill extraction")
            return []

        # 3. Build skill entry
        title = self._build_title(target, tool_chain)
        trigger = self._build_trigger(target, tool_chain)

        skill = SkillEntry(
            title=title,
            trigger=trigger,
            target=target,
            tool_chain=tool_chain,
            hyperparams=hyperparams,
            metrics=metrics,
            lessons=lessons,
            failure_recovery=failure_recovery,
            raw_snippets=self._collect_evidence_snippets(messages),
        )

        # 4. Deduplicate against existing skills
        if self._is_duplicate(skill):
            logger.info("Skill '%s' is a duplicate; merging instead", skill.title)
            self._merge_skill(skill)
            return []

        return [skill]

    def save_skill(self, skill: SkillEntry) -> Path:
        """Persist a SkillEntry to disk as a Markdown file."""
        path = self.skills_dir / f"{skill.skill_id}.md"
        path.write_text(skill.to_markdown(), encoding="utf-8")
        logger.info("Saved skill '%s' to %s", skill.title, path)
        return path

    def extract_and_save(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        session_id: str | None = None,
    ) -> list[Path]:
        """Convenience: extract skills and save them in one call."""
        skills = self.extract_from_session(messages, session_id=session_id)
        saved: list[Path] = []
        for skill in skills:
            saved.append(self.save_skill(skill))
        return saved

    def list_skills(self) -> list[Path]:
        """Return all skill files in the skills directory."""
        return sorted(self.skills_dir.glob("*.md"))

    def load_skill(self, path: Path) -> str:
        """Load a skill file and return its content."""
        return path.read_text(encoding="utf-8")

    def search_skills(self, query: str, *, top_k: int = 5) -> list[tuple[Path, float]]:
        """
        Simple keyword-based skill search.

        Returns paths with a relevance score (higher = better match).
        """
        if _RUST_AVAILABLE and _rust_search_skills is not None:
            try:
                res = _rust_search_skills(str(self.skills_dir), query, top_k)
                return [(Path(path_str), score) for path_str, score in res]
            except Exception as e:
                logger.warning(
                    f"Rust search_skills failed, falling back to Python: {e}"
                )

        query_lower = query.lower()
        query_terms = set(query_lower.split())
        results: list[tuple[Path, float]] = []

        for path in self.list_skills():
            content = path.read_text(encoding="utf-8").lower()
            score = sum(1.0 for term in query_terms if term in content)
            # Bonus for exact target match
            if query_lower in content:
                score += 3.0
            if score > 0:
                results.append((path, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_skills_context_prompt(self, query: str, *, top_k: int = 3) -> str:
        """
        Generate a formatted context block from relevant historical skills.

        This is injected into the agent's context at session start so it
        can leverage previously learned binder-design strategies.
        """
        matches = self.search_skills(query, top_k=top_k)
        if not matches:
            return ""

        lines: list[str] = [
            "==================================================",
            "🧠 SKILLS MEMORY — Previously Learned Strategies",
            "==================================================",
        ]

        for i, (path, _score) in enumerate(matches, 1):
            content = path.read_text(encoding="utf-8").strip()
            # Truncate very long skills to avoid context bloat
            if len(content) > 2000:
                content = content[:2000] + "\n... (truncated)"
            lines.append(f"\n--- Skill {i} ({path.stem}) ---")
            lines.append(content)

        lines.append("\n==================================================")
        lines.append("Apply these learned strategies to guide your design decisions.")
        lines.append("==================================================")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_binder_design_session(self, messages: Sequence[dict[str, Any]]) -> bool:
        """Heuristic: does this conversation involve binder design tools?"""
        if _RUST_AVAILABLE and _rust_is_binder is not None:
            try:
                contents = [str(m.get("content", "")) for m in messages]
                return _rust_is_binder(contents)
            except Exception as e:
                logger.warning(
                    f"Rust is_binder_design_session failed, falling back to Python: {e}"
                )

        binder_keywords = [
            "binder",
            "bindcraft",
            "pxdesign",
            "rfd3",
            "boltzgen",
            "ipTM",
            "pLDDT",
            "interface_residues",
            "target_pdb",
            "protein design",
        ]
        text = " ".join(str(m.get("content", "")) for m in messages).lower()
        return sum(1 for kw in binder_keywords if kw in text) >= 2

    def _extract_target(self, messages: Sequence[dict[str, Any]]) -> str | None:
        """Try to identify the target protein from the conversation."""
        # Priority 1: PDB file references (e.g. "4ZQK.pdb")
        pdb_re = re.compile(r"([A-Za-z0-9_-]+)\.pdb", re.I)
        # Priority 2: Explicit "against <NAME>" or "target <NAME>" patterns
        against_re = re.compile(r"against\s+([A-Za-z0-9_-]+)", re.I)
        # "target: NAME" or "target NAME" — but skip if followed by
        # known non-target words (interface_residues, residues, etc.)
        _SKIP_TARGET_WORDS = {
            "interface_residues",
            "residues",
            "protein",
            "binder",
            "design",
            "structure",
            "sequence",
        }
        target_re = re.compile(r"target[:\s]+([A-Za-z0-9_-]+)", re.I)

        for msg in messages:
            content = str(msg.get("content", ""))
            # PDB first (most reliable)
            m = pdb_re.search(content)
            if m and m.group(1).lower() not in {
                "output",
                "result",
                "binder",
                "complex",
            }:
                return m.group(1)
            # "against X" pattern
            m = against_re.search(content)
            if m and m.group(1).lower() not in _SKIP_TARGET_WORDS:
                return m.group(1)

        # Fallback: "target: X" pattern
        for msg in messages:
            content = str(msg.get("content", ""))
            m = target_re.search(content)
            if m and m.group(1).lower() not in _SKIP_TARGET_WORDS:
                return m.group(1)
        return None

    def _extract_tool_chain(self, messages: Sequence[dict[str, Any]]) -> list[str]:
        """Detect the sequence of design tools used, in order."""
        chain: list[str] = []
        seen: set[str] = set()

        for msg in messages:
            content = str(msg.get("content", ""))
            for tool_name, pattern in _TOOL_CALL_PATTERNS:
                if pattern.search(content) and tool_name not in seen:
                    chain.append(tool_name)
                    seen.add(tool_name)
        return chain

    def _extract_hyperparams(
        self, messages: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        """Extract key hyperparameter values from the conversation."""
        params: dict[str, Any] = {}
        for msg in messages:
            content = str(msg.get("content", ""))
            for key in _HYPERPARAM_KEYS:
                # Match patterns like "num_samples=100" or "num_samples: 100"
                pattern = re.compile(
                    rf'{key}["\s:=]+(\d+(?:\.\d+)?%?)',
                    re.I,
                )
                m = pattern.search(content)
                if m and key not in params:
                    params[key] = m.group(1)
        return params

    def _extract_metrics(self, messages: Sequence[dict[str, Any]]) -> dict[str, str]:
        """Extract final outcome metrics."""
        metrics: dict[str, str] = {}
        # Scan in reverse order to get the latest values
        for msg in reversed(messages):
            content = str(msg.get("content", ""))
            for metric_name, pattern in _METRIC_PATTERNS:
                if metric_name not in metrics:
                    m = pattern.search(content)
                    if m:
                        metrics[metric_name] = m.group(1)
        return metrics

    def _extract_lessons(self, messages: Sequence[dict[str, Any]]) -> list[str]:
        """Extract key lessons from assistant messages (ACE-enhanced)."""
        lessons: list[str] = []
        lesson_patterns = [
            re.compile(
                r"(?:lesson|key\s*takeaway|note|important|learned)[:\s]+(.+)", re.I
            ),
            re.compile(r"(?:recommend|suggest|best\s*practice)[:\s]+(.+)", re.I),
            re.compile(r"(?:worked\s*well|successful|effective)[:\s]*(.+)", re.I),
            # ACE: additional patterns for richer extraction
            re.compile(r"(?:conclusion|finding|observation)[:\s]+(.+)", re.I),
            re.compile(r"(?:avoid|don'?t|never|prevent)[:\s]+(.+)", re.I),
            re.compile(
                r"(?:optimal|best\s*(?:result|outcome|performance))[:\s]*(.+)", re.I
            ),
            re.compile(r"(?:increase|decrease|improve|reduce)\w*\s+(.+)", re.I),
        ]
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            content = str(msg.get("content", ""))
            for pattern in lesson_patterns:
                for m in pattern.finditer(content):
                    lesson = m.group(1).strip().rstrip(".")
                    # ACE: enforce minimum length to avoid trivial lessons
                    if len(lesson) > 15 and lesson not in lessons:
                        lessons.append(lesson)
        return lessons[:15]

    def _extract_failure_recovery(
        self, messages: Sequence[dict[str, Any]]
    ) -> list[str]:
        """Detect OOM or other failures and the recovery actions taken."""
        recoveries: list[str] = []
        for i, msg in enumerate(messages):
            content = str(msg.get("content", ""))
            if _OOM_RE.search(content):
                recovery = "Detected CUDA OOM error"
                # Check subsequent messages for recovery
                for j in range(i + 1, min(i + 5, len(messages))):
                    next_content = str(messages[j].get("content", ""))
                    if _RECOVERY_RE.search(next_content):
                        m = _RECOVERY_RE.search(next_content)
                        recovery += f" → recovered by: {m.group(0)}"
                        break
                if recovery not in recoveries:
                    recoveries.append(recovery)
        return recoveries

    def _collect_evidence_snippets(
        self, messages: Sequence[dict[str, Any]]
    ) -> list[str]:
        """Collect the most informative snippets from the conversation."""
        snippets: list[str] = []
        for msg in messages:
            content = str(msg.get("content", ""))
            if len(content) < 50:
                continue
            # Prioritise tool result messages with metrics
            has_metric = any(p.search(content) for _, p in _METRIC_PATTERNS)
            if has_metric:
                snippets.append(content[:500])
        return snippets[:8]

    def _build_title(self, target: str | None, tool_chain: list[str]) -> str:
        target_label = target or "Generic"
        chain_label = "+".join(tool_chain[:3])
        return f"{target_label} Binder Design via {chain_label}"

    def _build_trigger(self, target: str | None, tool_chain: list[str]) -> str:
        parts = ["When designing protein binders"]
        if target:
            parts.append(f"against target {target}")
        if tool_chain:
            parts.append(f"using {', '.join(tool_chain)}")
        return " ".join(parts) + "."

    def _is_duplicate(self, skill: SkillEntry) -> bool:
        """Check if a very similar skill already exists."""
        for path in self.list_skills():
            content = path.read_text(encoding="utf-8").lower()
            # Match on title + tool chain overlap
            if skill.title.lower() in content:
                chain_overlap = sum(1 for t in skill.tool_chain if t.lower() in content)
                if chain_overlap >= len(skill.tool_chain) * 0.7:
                    return True
        return False

    def _merge_skill(self, new_skill: SkillEntry) -> None:
        """Merge new lessons/metrics into an existing skill file."""
        for path in self.list_skills():
            content = path.read_text(encoding="utf-8")
            if new_skill.title.lower() not in content.lower():
                continue

            # Append new lessons if any
            if new_skill.lessons or new_skill.metrics:
                append_parts: list[str] = []
                if new_skill.metrics:
                    metrics_str = ", ".join(
                        f"{k}={v}" for k, v in new_skill.metrics.items()
                    )
                    append_parts.append(f"\n- **Updated Metrics:** {metrics_str}")
                for lesson in new_skill.lessons:
                    append_parts.append(f"- {lesson}")

                with open(path, "a", encoding="utf-8") as f:
                    f.write(
                        f"\n\n## Update ({new_skill.created_at})\n"
                        + "\n".join(append_parts)
                        + "\n"
                    )
                logger.info("Merged skill updates into %s", path)
            break
