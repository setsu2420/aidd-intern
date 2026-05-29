"""
Knowledge Wiki — LLM Wiki pattern for accumulating binder-design experience.

Architecture (inspired by Karpathy's LLM Wiki / nashsu/llm_wiki + ACE paper):
  Raw Layer    → Ingest from session logs, MemU records, and tool outputs.
  Wiki Layer   → Process into atomic, self-contained knowledge units
                  (one entry per target / tool chain / strategy).
  Index Layer  → Keyword + tag-based structured index for fast retrieval.

ACE (Agentic Context Engineering) enhancements:
  • Bullet-style entries with helpful/harmful effectiveness tracking
  • Incremental Delta updates instead of full rewrites
  • Grow-and-Refine with anti-collapse guards (content fingerprint + min length)
  • Reflector-driven ingestion: structured reflection reports → wiki updates
  • Playbook context mode for session injection

Each knowledge entry is stored as a YAML file with a standard schema so the
agent can search, load, and apply historical experience during new sessions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

try:
    from aidd_intern_core import search_wiki_entries_rust as _rust_search_wiki

    _RUST_AVAILABLE = True
except ImportError:
    _rust_search_wiki = None
    _RUST_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WIKI_DIR = Path(__file__).resolve().parent.parent / "knowledge_wiki"
ENTRIES_DIR = WIKI_DIR / "entries"
INDEX_FILE = WIKI_DIR / "index.json"

# ACE: minimum content length to prevent context collapse
_MIN_LESSON_LENGTH = 8
_MIN_CONTENT_FINGERPRINT_LEN = 20


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DeltaRecord:
    """ACE-inspired incremental update record for a knowledge entry."""

    action: (
        str  # "add_lesson" | "update_param" | "update_outcome" | "add_tag" | "refine"
    )
    field: str
    old_value: Any = None
    new_value: Any = None
    source: str = ""  # "reflector" | "session" | "manual"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class KnowledgeEntry:
    """
    An atomic, self-contained knowledge unit in the Wiki.

    Schema follows the LLM-Wiki principle + ACE Bullet enhancements:
    - Each entry is fully self-describing
    - Context travels with the entry (metadata)
    - Format is consistent across all entries
    - helpful/harmful counters track real-world effectiveness
    - delta_history records incremental changes
    - content_fingerprint guards against context collapse
    """

    id: str
    title: str
    category: str  # "target", "tool_chain", "strategy", "failure_mode", "benchmark"
    target: str | None = None
    tool_chain: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, str] = field(default_factory=dict)
    lessons: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_session: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    version: int = 1
    # --- ACE Bullet enhancements ---
    helpful_count: int = 0
    harmful_count: int = 0
    delta_history: list[dict[str, Any]] = field(default_factory=list)
    content_fingerprint: str = ""

    def to_yaml_dict(self) -> dict[str, Any]:
        """Serialise to a dict suitable for YAML/JSON output."""
        d = asdict(self)
        # Remove None values and empty collections for cleaner output
        return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}

    def to_json(self) -> str:
        return json.dumps(self.to_yaml_dict(), indent=2, ensure_ascii=False)

    def summary(self) -> str:
        """One-line human-readable summary."""
        parts = [f"[{self.category}] {self.title}"]
        if self.target:
            parts.append(f"target={self.target}")
        if self.tool_chain:
            parts.append(f"tools={'→'.join(self.tool_chain)}")
        if self.outcome:
            metrics = ", ".join(f"{k}={v}" for k, v in list(self.outcome.items())[:3])
            parts.append(metrics)
        if self.helpful_count or self.harmful_count:
            parts.append(f"↗{self.helpful_count}↘{self.harmful_count}")
        return " | ".join(parts)

    # ---- ACE effectiveness tracking ----

    @property
    def effectiveness_score(self) -> float:
        """Net effectiveness: helpful − harmful, normalised to [−1, 1]."""
        total = self.helpful_count + self.harmful_count
        if total == 0:
            return 0.0
        return (self.helpful_count - self.harmful_count) / total

    def mark_helpful(self) -> None:
        self.helpful_count += 1

    def mark_harmful(self) -> None:
        self.harmful_count += 1

    # ---- ACE anti-collapse guards ----

    def compute_fingerprint(self) -> str:
        """Compute a content fingerprint to detect collapse."""
        raw = (
            self.title
            + "|"
            + " ".join(self.lessons)
            + "|"
            + json.dumps(self.params, sort_keys=True)
            + "|"
            + json.dumps(self.outcome, sort_keys=True)
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def check_collapse(self) -> bool:
        """Return True if the entry appears to have collapsed."""
        total_lesson_len = sum(len(lesson) for lesson in self.lessons)
        if self.lessons and total_lesson_len < _MIN_LESSON_LENGTH * len(self.lessons):
            return True
        fp = self.compute_fingerprint()
        if (
            self.content_fingerprint
            and fp == self.content_fingerprint
            and self.version > 3
        ):
            # Fingerprint unchanged across many versions → possible stale/collapsed
            return True
        return False

    def record_delta(self, delta: DeltaRecord) -> None:
        """Append a delta record to the history (keeps last 50)."""
        self.delta_history.append(asdict(delta))
        # Trim to avoid unbounded growth
        if len(self.delta_history) > 50:
            self.delta_history = self.delta_history[-50:]
        self.content_fingerprint = self.compute_fingerprint()


# ---------------------------------------------------------------------------
# Knowledge Wiki
# ---------------------------------------------------------------------------


class KnowledgeWiki:
    """
    Manages a local knowledge base of binder-design experience.

    Provides:
    - ``ingest()``: add new experience from sessions
    - ``search()``: keyword + tag retrieval
    - ``get_context_prompt()``: formatted prompt block for the agent
    """

    def __init__(self, wiki_dir: Path | None = None) -> None:
        self.wiki_dir = wiki_dir or WIKI_DIR
        self.entries_dir = self.wiki_dir / "entries"
        self.index_file = self.wiki_dir / "index.json"
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, Any] = self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        *,
        title: str,
        category: str = "strategy",
        target: str | None = None,
        tool_chain: list[str] | None = None,
        params: dict[str, Any] | None = None,
        outcome: dict[str, str] | None = None,
        lessons: list[str] | None = None,
        tags: list[str] | None = None,
        source_session: str | None = None,
    ) -> KnowledgeEntry:
        """
        Ingest a new knowledge entry or merge with an existing one.

        Returns the created or updated entry.
        """
        entry_id = self._make_id(title, target)

        # Check for existing entry to merge
        existing = self._find_by_id(entry_id)
        if existing:
            return self._merge_entry(
                existing,
                params=params,
                outcome=outcome,
                lessons=lessons,
                tags=tags,
            )

        entry = KnowledgeEntry(
            id=entry_id,
            title=title,
            category=category,
            target=target,
            tool_chain=tool_chain or [],
            params=params or {},
            outcome=outcome or {},
            lessons=lessons or [],
            tags=self._auto_tags(target, tool_chain, category, tags),
            source_session=source_session,
        )

        self._save_entry(entry)
        self._update_index(entry)
        logger.info("Ingested knowledge entry: %s", entry.summary())
        return entry

    def ingest_from_session(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        session_id: str | None = None,
    ) -> list[KnowledgeEntry]:
        """
        Automatically extract and ingest knowledge from a session's messages.
        """
        from agent.core.skill_extractor import SkillExtractor

        extractor = SkillExtractor()
        skills = extractor.extract_from_session(messages, session_id=session_id)

        entries: list[KnowledgeEntry] = []
        for skill in skills:
            entry = self.ingest(
                title=skill.title,
                category="strategy",
                target=skill.target,
                tool_chain=skill.tool_chain,
                params=skill.hyperparams,
                outcome=skill.metrics,
                lessons=skill.lessons,
                tags=skill.failure_recovery[:3] if skill.failure_recovery else None,
                source_session=session_id,
            )
            entries.append(entry)
        return entries

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        target: str | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeEntry]:
        """
        Search the wiki by keyword matching.

        Parameters
        ----------
        query:
            Free-text search query.
        category:
            Optional category filter.
        target:
            Optional target protein filter.
        top_k:
            Maximum number of results.
        """
        if _RUST_AVAILABLE and _rust_search_wiki is not None:
            try:
                current_time = datetime.now(timezone.utc).isoformat()
                jsons = _rust_search_wiki(
                    str(self.entries_dir),
                    query,
                    current_time,
                    category=category,
                    target=target,
                    top_k=top_k,
                )
                entries = []
                for entry_json in jsons:
                    try:
                        data = json.loads(entry_json)
                        entries.append(KnowledgeEntry(**data))
                    except Exception as e:
                        logger.warning(f"Failed to parse Rust-returned entry JSON: {e}")
                return entries
            except Exception as e:
                logger.warning(f"Rust search_wiki failed, falling back to Python: {e}")

        query_lower = query.lower()
        query_terms = set(query_lower.split())
        scored: list[tuple[KnowledgeEntry, float]] = []

        for entry in self._load_all_entries():
            # Category filter
            if category and entry.category != category:
                continue
            # Target filter
            if target and entry.target and target.lower() not in entry.target.lower():
                continue

            score = self._score_entry(entry, query_terms, query_lower)
            if score > 0:
                scored.append((entry, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, _ in scored[:top_k]]

    def get_context_prompt(
        self,
        query: str,
        *,
        target: str | None = None,
        top_k: int = 3,
        category: str | None = None,
    ) -> str:
        """
        Generate a formatted prompt block with relevant historical experience.

        This is injected into the agent's system prompt or context at
        session start.
        """
        entries = self.search(query, target=target, top_k=top_k, category=category)
        if not entries:
            return ""

        lines: list[str] = [
            "==================================================",
            "📚 BINDER DESIGN KNOWLEDGE WIKI — Historical Experience",
            "==================================================",
        ]

        for i, entry in enumerate(entries, 1):
            lines.append(f"\n### Entry {i}: {entry.title}")
            if entry.target:
                lines.append(f"  Target: {entry.target}")
            if entry.tool_chain:
                lines.append(f"  Tool Chain: {' → '.join(entry.tool_chain)}")
            if entry.params:
                params_str = ", ".join(f"{k}={v}" for k, v in entry.params.items())
                lines.append(f"  Params: {params_str}")
            if entry.outcome:
                outcome_str = ", ".join(f"{k}={v}" for k, v in entry.outcome.items())
                lines.append(f"  Outcome: {outcome_str}")
            if entry.lessons:
                lines.append("  Lessons:")
                for lesson in entry.lessons[:5]:
                    lines.append(f"    • {lesson}")

        lines.append("\n==================================================")
        lines.append("Use this historical experience to guide your design decisions.")
        lines.append("==================================================")
        return "\n".join(lines)

    def list_entries(self) -> list[KnowledgeEntry]:
        """Return all entries in the wiki."""
        return self._load_all_entries()

    def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        """Get a specific entry by ID."""
        return self._find_by_id(entry_id)

    @property
    def entry_count(self) -> int:
        return len(list(self.entries_dir.glob("*.json")))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_id(self, title: str, target: str | None) -> str:
        raw = f"{title}|{target or ''}".lower()
        return "wiki-" + hashlib.md5(raw.encode()).hexdigest()[:10]

    def _load_index(self) -> dict[str, Any]:
        if self.index_file.exists():
            try:
                return json.loads(self.index_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Corrupted index file; rebuilding")
        return {"entries": {}, "tags": {}, "updated_at": None}

    def _save_index(self) -> None:
        self._index["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.index_file.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _save_entry(self, entry: KnowledgeEntry) -> Path:
        path = self.entries_dir / f"{entry.id}.json"
        path.write_text(entry.to_json(), encoding="utf-8")
        return path

    def _load_entry(self, path: Path) -> KnowledgeEntry | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return KnowledgeEntry(**data)
        except Exception as e:
            logger.warning("Failed to load entry %s: %s", path, e)
            return None

    def _load_all_entries(self) -> list[KnowledgeEntry]:
        entries: list[KnowledgeEntry] = []
        for path in sorted(self.entries_dir.glob("*.json")):
            entry = self._load_entry(path)
            if entry:
                entries.append(entry)
        return entries

    def _find_by_id(self, entry_id: str) -> KnowledgeEntry | None:
        path = self.entries_dir / f"{entry_id}.json"
        if path.exists():
            return self._load_entry(path)
        return None

    def _update_index(self, entry: KnowledgeEntry) -> None:
        self._index.setdefault("entries", {})[entry.id] = {
            "title": entry.title,
            "category": entry.category,
            "target": entry.target,
            "tags": entry.tags,
        }
        # Update tag index
        tags_index = self._index.setdefault("tags", {})
        for tag in entry.tags:
            tags_index.setdefault(tag, []).append(entry.id)
        self._save_index()

    def apply_delta(
        self,
        entry_id: str,
        *,
        action: str,
        field_name: str,
        new_value: Any,
        old_value: Any = None,
        source: str = "session",
    ) -> KnowledgeEntry | None:
        """
        ACE-inspired incremental Delta update.

        Apply a single, targeted edit to an existing entry instead of
        rewriting the whole entry.  Records the change in ``delta_history``
        and updates the content fingerprint.

        Parameters
        ----------
        entry_id:
            Target entry ID.
        action:
            One of ``add_lesson``, ``update_param``, ``update_outcome``,
            ``add_tag``, ``refine``, ``remove_lesson``.
        field_name:
            The entry field being edited (e.g. ``"lessons"``, ``"params"``).
        new_value:
            The new value to apply.
        old_value:
            Previous value (for the delta record).
        source:
            Origin of the change (``"reflector"``, ``"session"``, ``"manual"``).

        Returns the updated entry, or ``None`` if the entry was not found.
        """
        existing = self._find_by_id(entry_id)
        if existing is None:
            logger.warning("apply_delta: entry %s not found", entry_id)
            return None

        delta = DeltaRecord(
            action=action,
            field=field_name,
            old_value=old_value,
            new_value=new_value,
            source=source,
        )

        # Apply the edit
        if action == "add_lesson" and isinstance(new_value, str):
            if len(new_value) < _MIN_LESSON_LENGTH:
                logger.debug("Skipping short lesson (%d chars)", len(new_value))
                return existing
            if new_value not in existing.lessons:
                existing.lessons.append(new_value)
        elif action == "remove_lesson" and isinstance(new_value, str):
            existing.lessons = [
                lesson for lesson in existing.lessons if lesson != new_value
            ]
        elif action == "update_param":
            old = existing.params.get(field_name)
            existing.params[field_name] = new_value
            delta.old_value = old
        elif action == "update_outcome":
            old = existing.outcome.get(field_name)
            existing.outcome[field_name] = new_value
            delta.old_value = old
        elif action == "add_tag" and isinstance(new_value, str):
            if new_value not in existing.tags:
                existing.tags.append(new_value)
        elif action == "refine":
            # General refinement: replace field value entirely
            if hasattr(existing, field_name):
                delta.old_value = getattr(existing, field_name)
                setattr(existing, field_name, new_value)

        existing.record_delta(delta)
        existing.version += 1
        existing.updated_at = datetime.now(timezone.utc).isoformat()

        # Anti-collapse: reject update if it would collapse the entry
        if existing.check_collapse():
            logger.warning(
                "Delta rejected: entry '%s' collapse detected after %s on %s",
                existing.title,
                action,
                field_name,
            )
            # Revert the delta from history but keep the version bump
            if existing.delta_history:
                existing.delta_history.pop()

        self._save_entry(existing)
        self._update_index(existing)
        logger.info(
            "Delta applied (%s.%s, v%d) to '%s'",
            action,
            field_name,
            existing.version,
            existing.title,
        )
        return existing

    def ingest_reflector_report(
        self,
        report: Any,
        *,
        source_session: str | None = None,
    ) -> list[KnowledgeEntry]:
        """
        Ingest a :class:`~agent.core.reflector.ReflectionReport` into the wiki.

        This is the ACE Curator role: take structured reflections and turn
        them into incremental wiki updates rather than raw session dumps.

        Parameters
        ----------
        report:
            A ``ReflectionReport`` instance (or duck-typed dict).
        source_session:
            Optional session identifier.

        Returns list of created/updated entries.
        """
        # Accept both dataclass and dict
        if hasattr(report, "insights"):
            insights = report.insights
            strategy_updates = getattr(report, "strategy_updates", [])
            new_strategies = getattr(report, "new_strategies", [])
            anti_patterns = getattr(report, "anti_patterns", [])
        elif isinstance(report, dict):
            insights = report.get("insights", [])
            strategy_updates = report.get("strategy_updates", [])
            new_strategies = report.get("new_strategies", [])
            anti_patterns = report.get("anti_patterns", [])
        else:
            return []

        entries: list[KnowledgeEntry] = []

        # 1. Apply insights as lessons to matching entries
        for insight in insights:
            if not isinstance(insight, dict):
                continue
            category = insight.get("category", "strategy")
            target = insight.get("target")
            content = insight.get("content", "")
            if not content:
                continue

            entry_id = self._make_id(insight.get("title", content[:60]), target)
            existing = self._find_by_id(entry_id)
            if existing:
                updated = self.apply_delta(
                    entry_id,
                    action="add_lesson",
                    field_name="lessons",
                    new_value=content,
                    source="reflector",
                )
                if updated:
                    entries.append(updated)
            else:
                entry = self.ingest(
                    title=insight.get("title", content[:60]),
                    category=category,
                    target=target,
                    lessons=[content],
                    source_session=source_session,
                )
                entries.append(entry)

        # 2. Strategy updates → apply as deltas to existing entries
        for update in strategy_updates:
            if not isinstance(update, dict):
                continue
            entry_id = update.get("entry_id")
            if not entry_id:
                continue
            for lesson in update.get("add_lessons", []):
                self.apply_delta(
                    entry_id,
                    action="add_lesson",
                    field_name="lessons",
                    new_value=lesson,
                    source="reflector",
                )
            for key, val in update.get("update_params", {}).items():
                self.apply_delta(
                    entry_id,
                    action="update_param",
                    field_name=key,
                    new_value=val,
                    source="reflector",
                )

        # 3. New strategies → create fresh entries
        for strategy in new_strategies:
            if not isinstance(strategy, dict):
                continue
            entry = self.ingest(
                title=strategy.get("title", "Reflected strategy"),
                category="strategy",
                target=strategy.get("target"),
                tool_chain=strategy.get("tool_chain", []),
                params=strategy.get("params", {}),
                lessons=strategy.get("lessons", []),
                source_session=source_session,
            )
            entries.append(entry)

        # 4. Anti-patterns → create failure_mode entries
        for pattern in anti_patterns:
            if not isinstance(pattern, dict):
                continue
            entry = self.ingest(
                title=f"Anti-pattern: {pattern.get('description', 'unknown')[:50]}",
                category="failure_mode",
                target=pattern.get("target"),
                lessons=[
                    f"Avoid: {pattern.get('description', '')}",
                    f"Instead: {pattern.get('recommendation', '')}",
                ],
                source_session=source_session,
            )
            entries.append(entry)

        logger.info(
            "Reflector report ingested: %d entries created/updated", len(entries)
        )
        return entries

    def get_playbook_prompt(
        self,
        query: str,
        *,
        target: str | None = None,
        top_k: int = 5,
        min_effectiveness: float = -0.5,
    ) -> str:
        """
        ACE playbook mode: generate a structured, effectiveness-ranked
        context block for session injection.

        Unlike :meth:`get_context_prompt`, this ranks entries by
        ``effectiveness_score`` and filters out entries with poor track
        records (harmful > helpful by a wide margin).

        Parameters
        ----------
        query:
            Search query.
        target:
            Optional target filter.
        top_k:
            Maximum entries to include.
        min_effectiveness:
            Minimum effectiveness score to include. Set to ``-1.0`` to
            include all entries.
        """
        entries = self.search(query, target=target, top_k=top_k * 2)

        # Filter by effectiveness and sort
        entries = [e for e in entries if e.effectiveness_score >= min_effectiveness]
        # Sort: effectiveness first, then version (proxy for maturity)
        entries.sort(
            key=lambda e: (e.effectiveness_score, e.version),
            reverse=True,
        )
        entries = entries[:top_k]

        if not entries:
            return ""

        lines: list[str] = [
            "==================================================",
            "📋 BINDER DESIGN PLAYBOOK — Verified Strategies (ACE)",
            "==================================================",
        ]

        for i, entry in enumerate(entries, 1):
            eff_label = f"[↗{entry.helpful_count}" + (
                f"/↘{entry.harmful_count}]" if entry.harmful_count else "]"
            )
            lines.append(f"\n### #{i}: {entry.title}  {eff_label}")
            if entry.target:
                lines.append(f"  Target: {entry.target}")
            if entry.tool_chain:
                lines.append(f"  Tool Chain: {' → '.join(entry.tool_chain)}")
            if entry.params:
                params_str = ", ".join(f"{k}={v}" for k, v in entry.params.items())
                lines.append(f"  Recommended Params: {params_str}")
            if entry.outcome:
                outcome_str = ", ".join(f"{k}={v}" for k, v in entry.outcome.items())
                lines.append(f"  Typical Outcome: {outcome_str}")
            if entry.lessons:
                lines.append("  Key Lessons:")
                for lesson in entry.lessons[:5]:
                    lines.append(f"    • {lesson}")

        lines.append("\n==================================================")
        lines.append(
            "These strategies are ranked by verified effectiveness. "
            "Prefer higher-ranked strategies for new designs."
        )
        lines.append("==================================================")
        return "\n".join(lines)

    def _merge_entry(
        self,
        existing: KnowledgeEntry,
        *,
        params: dict[str, Any] | None = None,
        outcome: dict[str, str] | None = None,
        lessons: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> KnowledgeEntry:
        """Grow-and-refine: merge new data into existing entry via deltas."""
        if params:
            for key, val in params.items():
                self.apply_delta(
                    existing.id,
                    action="update_param",
                    field_name=key,
                    new_value=val,
                    old_value=existing.params.get(key),
                    source="session",
                )
        if outcome:
            for key, val in outcome.items():
                self.apply_delta(
                    existing.id,
                    action="update_outcome",
                    field_name=key,
                    new_value=val,
                    old_value=existing.outcome.get(key),
                    source="session",
                )
        if lessons:
            for lesson in lessons:
                self.apply_delta(
                    existing.id,
                    action="add_lesson",
                    field_name="lessons",
                    new_value=lesson,
                    source="session",
                )
        if tags:
            for tag in tags:
                self.apply_delta(
                    existing.id,
                    action="add_tag",
                    field_name="tags",
                    new_value=tag,
                    source="session",
                )

        # Reload to get the final state after all deltas
        updated = self._find_by_id(existing.id)
        if updated is None:
            return existing
        logger.info(
            "Merged update (v%d) into entry: %s", updated.version, updated.title
        )
        return updated

    def _score_entry(
        self,
        entry: KnowledgeEntry,
        query_terms: set[str],
        query_lower: str,
    ) -> float:
        """Score an entry against a query (ACE: includes effectiveness)."""
        score = 0.0

        # Full query match (high weight)
        searchable = (
            f"{entry.title} {entry.target or ''} {' '.join(entry.tags)}".lower()
        )
        if query_lower in searchable:
            score += 5.0

        # Term-level matching
        for term in query_terms:
            if term in searchable:
                score += 1.0
            if term in json.dumps(entry.params).lower():
                score += 0.5
            if term in " ".join(entry.lessons).lower():
                score += 1.0
            if entry.tool_chain and any(term in t.lower() for t in entry.tool_chain):
                score += 1.0

        # ACE: effectiveness bonus — proven strategies score higher
        if entry.helpful_count > 0:
            score += entry.effectiveness_score * 2.0

        # Recency bonus (newer entries slightly preferred)
        try:
            age_days = (
                datetime.now(timezone.utc) - datetime.fromisoformat(entry.created_at)
            ).days
            if age_days < 7:
                score += 1.0
            elif age_days < 30:
                score += 0.5
        except (ValueError, TypeError):
            pass

        return score

    def _auto_tags(
        self,
        target: str | None,
        tool_chain: list[str] | None,
        category: str,
        extra_tags: list[str] | None,
    ) -> list[str]:
        tags: list[str] = [category]
        if target:
            tags.append(target.lower())
        if tool_chain:
            tags.extend(tool_chain[:5])
        if extra_tags:
            for t in extra_tags:
                if t not in tags:
                    tags.append(t)
        return tags


# ---------------------------------------------------------------------------
# Wiki search tool handler (for agent integration)
# ---------------------------------------------------------------------------

KNOWLEDGE_WIKI_TOOL_SPEC = {
    "name": "knowledge_wiki_search",
    "description": (
        "Search the Binder Design Knowledge Wiki for historical experience, "
        "successful strategies, hyperparameter recommendations, and lessons learned "
        "from past design campaigns. Use this to leverage accumulated experience "
        "when planning new binder design workflows."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search query describing what experience or strategy to find. "
                    "Examples: 'PD-L1 binder design', 'BindCraft optimization', 'high ipTM strategies'."
                ),
            },
            "target": {
                "type": "string",
                "description": "Optional target protein name to filter results.",
            },
            "category": {
                "type": "string",
                "enum": [
                    "target",
                    "tool_chain",
                    "strategy",
                    "failure_mode",
                    "benchmark",
                ],
                "description": "Optional category filter.",
            },
            "top_k": {
                "type": "integer",
                "default": 3,
                "description": "Maximum number of results to return.",
            },
        },
        "required": ["query"],
    },
}


async def knowledge_wiki_search_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    """Tool handler: search the knowledge wiki and return formatted results."""
    query = arguments["query"]
    target = arguments.get("target")
    category = arguments.get("category")
    top_k = arguments.get("top_k", 3)

    try:
        wiki = KnowledgeWiki()
        if wiki.entry_count == 0:
            return (
                "Knowledge Wiki is empty. No historical experience recorded yet. "
                "Complete a successful binder design session to start accumulating knowledge.",
                True,
            )

        entries = wiki.search(query, category=category, target=target, top_k=top_k)
        if not entries:
            return f"No matching entries found for query: '{query}'", True

        prompt = wiki.get_context_prompt(query, target=target, top_k=top_k)
        return prompt, True
    except Exception as e:
        return f"Error searching knowledge wiki: {e}", False
