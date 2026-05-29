"""Tests for the Knowledge Wiki (LLM Wiki pattern)."""

from __future__ import annotations

import json
from pathlib import Path

from agent.core.knowledge_wiki import KnowledgeEntry, KnowledgeWiki


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_binder_messages() -> list[dict]:
    """Synthesise a realistic binder-design conversation."""
    return [
        {
            "role": "user",
            "content": "Design a binder against PD-L1 (PDB: 4ZQK.pdb). "
            "Target interface_residues: 54,56,58,115,117,121",
        },
        {
            "role": "assistant",
            "content": "Starting binder design for PD-L1 target. "
            "I will use run_bindcraft with binder_length=80 and iterations=50.",
        },
        {
            "role": "tool",
            "content": "BindCraft run completed. Generated 3 designs. "
            "num_samples=50, binder_length=80",
        },
        {
            "role": "assistant",
            "content": "Running orthogonal validation with run_chai1 on all candidates.",
        },
        {
            "role": "tool",
            "content": "Chai-1 results: ipTM: 0.85, pLDDT: 88.2, pAE: 4.1, clashes: 0",
        },
        {
            "role": "assistant",
            "content": "Good results from Chai-1. Now running run_protenix for cross-validation.",
        },
        {
            "role": "tool",
            "content": "Protenix results: ipTM: 0.82, pLDDT: 85.6, pAE: 5.3",
        },
        {
            "role": "assistant",
            "content": "Both models confirm high-quality design. "
            "Key takeaway: interface_residues selection is critical for PD-L1. "
            "Recommend using dual-model validation for all candidates. "
            "Success rate: 60%",
        },
    ]


# ---------------------------------------------------------------------------
# Tests: KnowledgeEntry
# ---------------------------------------------------------------------------


class TestKnowledgeEntry:
    def test_entry_id_format(self):
        entry = KnowledgeEntry(
            id="wiki-abc123", title="PD-L1 Binder Strategy", category="strategy"
        )
        assert entry.id.startswith("wiki-")
        assert entry.title == "PD-L1 Binder Strategy"

    def test_to_json_roundtrip(self):
        entry = KnowledgeEntry(
            id="wiki-test001",
            title="Test Entry",
            category="target",
            target="PD-L1",
            tool_chain=["run_bindcraft", "run_chai1"],
            params={"binder_length": "80"},
            outcome={"ipTM": "0.85"},
            lessons=["Interface selection matters"],
            tags=["binder", "pd-l1"],
        )
        json_str = entry.to_json()
        data = json.loads(json_str)
        assert data["title"] == "Test Entry"
        assert data["category"] == "target"
        assert "PD-L1" in data.get("target", "")

    def test_summary_format(self):
        entry = KnowledgeEntry(
            id="wiki-sum01",
            title="Summary Test",
            category="strategy",
            target="IL-7R",
            tool_chain=["run_pxdesign"],
            outcome={"ipTM": "0.80"},
        )
        summary = entry.summary()
        assert "[strategy]" in summary
        assert "Summary Test" in summary


# ---------------------------------------------------------------------------
# Tests: KnowledgeWiki
# ---------------------------------------------------------------------------


class TestKnowledgeWiki:
    def test_ingest_creates_entry(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        entry = wiki.ingest(
            title="PD-L1 Binder via BindCraft",
            category="strategy",
            target="PD-L1",
            tool_chain=["run_bindcraft", "run_chai1"],
            params={"binder_length": "80"},
            outcome={"ipTM": "0.85"},
            lessons=["Interface residues are critical"],
            tags=["binder"],
        )
        assert entry.id.startswith("wiki-")
        assert entry.title == "PD-L1 Binder via BindCraft"
        assert wiki.entry_count == 1

    def test_ingest_deduplication(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        entry1 = wiki.ingest(
            title="Same Title", target="SameTarget", category="strategy"
        )
        entry2 = wiki.ingest(
            title="Same Title", target="SameTarget", category="strategy"
        )
        # Should merge rather than create duplicate
        assert entry1.id == entry2.id
        assert wiki.entry_count == 1

    def test_search_by_keyword(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        wiki.ingest(
            title="PD-L1 Binder Strategy",
            category="strategy",
            target="PD-L1",
            lessons=["Interface selection is key"],
        )
        wiki.ingest(
            title="IL-7R Binder Strategy",
            category="strategy",
            target="IL-7R",
            lessons=["Different target"],
        )

        results = wiki.search("PD-L1 binder")
        assert len(results) >= 1
        assert any("PD-L1" in (e.target or "") for e in results)

    def test_search_by_category(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        wiki.ingest(title="Strategy A", category="strategy", target="X")
        wiki.ingest(title="Failure Mode B", category="failure_mode", target="X")

        results = wiki.search("X", category="failure_mode")
        assert all(e.category == "failure_mode" for e in results)

    def test_search_by_target_filter(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        wiki.ingest(title="Entry A", target="PD-L1", category="strategy")
        wiki.ingest(title="Entry B", target="IL-7R", category="strategy")

        results = wiki.search("binder", target="PD-L1")
        assert all("PD-L1" in (e.target or "") for e in results)

    def test_get_context_prompt_empty(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        ctx = wiki.get_context_prompt("nonexistent query")
        assert ctx == ""

    def test_get_context_prompt_with_entries(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        wiki.ingest(
            title="PD-L1 Binder",
            category="strategy",
            target="PD-L1",
            tool_chain=["run_bindcraft"],
            outcome={"ipTM": "0.85"},
            lessons=["Important lesson"],
        )
        ctx = wiki.get_context_prompt("PD-L1 binder")
        assert "KNOWLEDGE WIKI" in ctx
        assert "PD-L1" in ctx
        assert "Important lesson" in ctx

    def test_list_entries(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        wiki.ingest(title="Entry 1", target="A", category="strategy")
        wiki.ingest(title="Entry 2", target="B", category="strategy")

        entries = wiki.list_entries()
        assert len(entries) == 2

    def test_get_entry_by_id(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        entry = wiki.ingest(title="Specific Entry", target="X", category="strategy")

        retrieved = wiki.get_entry(entry.id)
        assert retrieved is not None
        assert retrieved.title == "Specific Entry"

    def test_ingest_from_session(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        messages = _make_binder_messages()
        entries = wiki.ingest_from_session(messages, session_id="test-session-123")

        # Should extract at least one entry from a binder design session
        assert len(entries) >= 1
        # Entry should reference the target (PDB id or target name)
        all_text = " ".join((e.target or "") + " " + e.title for e in entries).lower()
        assert "pd-l1" in all_text or "4zqk" in all_text or "binder" in all_text

    def test_wiki_persistence(self, tmp_path: Path):
        # First wiki instance
        wiki1 = KnowledgeWiki(wiki_dir=tmp_path)
        wiki1.ingest(title="Persistent Entry", target="X", category="strategy")

        # Second wiki instance (simulates new session)
        wiki2 = KnowledgeWiki(wiki_dir=tmp_path)
        entries = wiki2.list_entries()
        assert len(entries) == 1
        assert entries[0].title == "Persistent Entry"

    def test_entry_version_increment(self, tmp_path: Path):
        wiki = KnowledgeWiki(wiki_dir=tmp_path)
        entry1 = wiki.ingest(title="Versioned", target="X", category="strategy")
        assert entry1.version == 1

        # Re-ingest with same id should merge and increment version
        entry2 = wiki.ingest(
            title="Versioned",
            target="X",
            category="strategy",
            lessons=["New lesson"],
        )
        assert entry2.version >= 2
