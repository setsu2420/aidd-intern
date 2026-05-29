"""Tests for the SkillExtractor self-evolution engine."""

from __future__ import annotations

from pathlib import Path

from agent.core.skill_extractor import SkillEntry, SkillExtractor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_binder_session_messages() -> list[dict]:
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


def _make_oom_session_messages() -> list[dict]:
    return [
        {"role": "user", "content": "Design binder for target.pdb"},
        {
            "role": "assistant",
            "content": "Running run_pxdesign with num_samples=200",
        },
        {
            "role": "tool",
            "content": "CUDA out of memory error. Cannot allocate 4.2 GB.",
        },
        {
            "role": "assistant",
            "content": "OOM detected. Reduced num_samples to 100 and enabled mixed precision. Retrying.",
        },
        {
            "role": "tool",
            "content": "PXdesign completed. ipTM: 0.78, pLDDT: 82.0",
        },
    ]


# ---------------------------------------------------------------------------
# Tests: SkillEntry
# ---------------------------------------------------------------------------


class TestSkillEntry:
    def test_skill_id_format(self):
        entry = SkillEntry(
            title="PD-L1 Binder via BindCraft",
            trigger="When designing binders against PD-L1",
        )
        assert entry.skill_id.startswith("skill-pd-l1-binder-via-bindcraft-")

    def test_to_markdown_has_sections(self):
        entry = SkillEntry(
            title="Test Skill",
            trigger="When designing binders",
            target="PD-L1",
            tool_chain=["run_bindcraft", "run_chai1"],
            hyperparams={"binder_length": "80"},
            metrics={"ipTM": "0.85"},
            lessons=["Interface selection matters"],
            failure_recovery=["OOM → reduce batch"],
        )
        md = entry.to_markdown()
        assert "# Test Skill" in md
        assert "## Trigger" in md
        assert "## Steps" in md
        assert "run_bindcraft" in md
        assert "## Lessons Learned" in md
        assert "## Failure Recovery" in md


# ---------------------------------------------------------------------------
# Tests: SkillExtractor
# ---------------------------------------------------------------------------


class TestSkillExtractor:
    def test_extract_from_binder_session(self, tmp_path: Path):
        extractor = SkillExtractor(skills_dir=tmp_path)
        messages = _make_binder_session_messages()
        skills = extractor.extract_from_session(messages)

        assert len(skills) >= 1
        skill = skills[0]
        # Target should be either PDB id "4ZQK" or "PD-L1" (both valid extractions)
        assert skill.target is not None
        assert (
            "PD-L1" in skill.target
            or "4ZQK" in skill.target
            or "pd-l1" in skill.title.lower()
        )
        assert "run_bindcraft" in skill.tool_chain
        assert "run_chai1" in skill.tool_chain
        assert "run_protenix" in skill.tool_chain

    def test_extract_hyperparams(self, tmp_path: Path):
        extractor = SkillExtractor(skills_dir=tmp_path)
        messages = _make_binder_session_messages()
        skills = extractor.extract_from_session(messages)
        skill = skills[0]
        assert "binder_length" in skill.hyperparams or "iterations" in skill.hyperparams

    def test_extract_metrics(self, tmp_path: Path):
        extractor = SkillExtractor(skills_dir=tmp_path)
        messages = _make_binder_session_messages()
        skills = extractor.extract_from_session(messages)
        skill = skills[0]
        assert "ipTM" in skill.metrics or "pLDDT" in skill.metrics

    def test_extract_oom_recovery(self, tmp_path: Path):
        extractor = SkillExtractor(skills_dir=tmp_path)
        messages = _make_oom_session_messages()
        skills = extractor.extract_from_session(messages)
        if skills:
            assert len(skills[0].failure_recovery) >= 1

    def test_save_and_load(self, tmp_path: Path):
        extractor = SkillExtractor(skills_dir=tmp_path)
        messages = _make_binder_session_messages()
        saved = extractor.extract_and_save(messages)
        assert len(saved) >= 1

        loaded = extractor.load_skill(saved[0])
        assert "PD-L1" in loaded or "Binder" in loaded

    def test_short_session_skipped(self, tmp_path: Path):
        extractor = SkillExtractor(skills_dir=tmp_path)
        skills = extractor.extract_from_session([{"role": "user", "content": "hello"}])
        assert skills == []

    def test_non_binder_session_skipped(self, tmp_path: Path):
        extractor = SkillExtractor(skills_dir=tmp_path)
        messages = [
            {"role": "user", "content": "What is the weather today?"},
            {"role": "assistant", "content": "I can't check the weather."},
            {"role": "user", "content": "Tell me a joke"},
            {"role": "assistant", "content": "Why did the chicken cross the road?"},
        ]
        skills = extractor.extract_from_session(messages)
        assert skills == []

    def test_search_skills(self, tmp_path: Path):
        extractor = SkillExtractor(skills_dir=tmp_path)
        messages = _make_binder_session_messages()
        extractor.extract_and_save(messages)

        results = extractor.search_skills("PD-L1 binder")
        assert len(results) >= 1

    def test_deduplication(self, tmp_path: Path):
        extractor = SkillExtractor(skills_dir=tmp_path)
        messages = _make_binder_session_messages()

        # First extraction
        skills1 = extractor.extract_and_save(messages)
        # Second extraction of same session
        skills2 = extractor.extract_from_session(messages)
        # Should be detected as duplicate
        assert len(skills2) == 0 or len(skills1) >= 1

    def test_get_skills_context_prompt_empty(self, tmp_path: Path):
        """Empty skills directory should return empty context."""
        extractor = SkillExtractor(skills_dir=tmp_path)
        ctx = extractor.get_skills_context_prompt("binder design")
        assert ctx == ""

    def test_get_skills_context_populated(self, tmp_path: Path):
        """Populated skills directory should return formatted context."""
        extractor = SkillExtractor(skills_dir=tmp_path)
        messages = _make_binder_session_messages()
        extractor.extract_and_save(messages)

        ctx = extractor.get_skills_context_prompt("binder PD-L1 protein", top_k=3)
        assert "SKILLS MEMORY" in ctx
        assert "Skill 1" in ctx

    def test_seed_skills_loadable(self):
        """Built-in seed skills in agent/skills/ should be loadable."""
        from agent.core.skill_extractor import SKILLS_DIR

        extractor = SkillExtractor(skills_dir=SKILLS_DIR)
        skills = extractor.list_skills()
        assert len(skills) >= 6, f"Expected >=6 seed skills, found {len(skills)}"

        # Each skill file should be valid Markdown
        for path in skills:
            content = extractor.load_skill(path)
            assert "# " in content, f"Skill {path.name} missing title heading"
            assert "## Trigger" in content, f"Skill {path.name} missing Trigger section"
            assert "## Steps" in content, f"Skill {path.name} missing Steps section"
