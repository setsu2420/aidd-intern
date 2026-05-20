"""Protein-design specialist roles."""

from __future__ import annotations

from agent.roles import RoleSpec


PROTEIN_DESIGN_ROLES = [
    RoleSpec(
        name="structural_biologist",
        description="Analyzes target structures, epitopes, glycans, and interface physics.",
        responsibilities=[
            "map PDB structures to design-relevant interface features",
            "identify hotspot residues and glycan/membrane approach constraints",
            "produce source-backed structural hypotheses",
        ],
        allowed_tools=["aidd_bio", "web_search", "protein_design_ace_playbook"],
        output_contract="structural_design_memo",
        max_context_tokens=18_000,
    ),
    RoleSpec(
        name="protein_designer",
        description="Chooses binder modalities and generation strategies.",
        responsibilities=[
            "select epitope and scaffold classes",
            "choose BindCraft, BoltzGen, PXdesign, or hybrid workflows",
            "define cheap and expensive filters before execution",
        ],
        allowed_tools=[
            "protein_design_ace_playbook",
            "run_pxdesign",
            "run_boltzgen",
            "run_bindcraft",
        ],
        output_contract="design_plan",
        max_context_tokens=18_000,
        can_write=True,
        can_run_gpu=True,
    ),
    RoleSpec(
        name="orthogonal_validator",
        description="Validates candidates with independent structural metrics.",
        responsibilities=[
            "compare Chai-1, Protenix, Rosetta, and Foldseek outputs",
            "reject single-model or reward-hacked candidates",
            "summarize final candidate diversity and risk",
        ],
        allowed_tools=["aidd_bio", "protein_design_ace_playbook"],
        output_contract="orthogonal_validation_report",
        max_context_tokens=16_000,
        requires_verification=False,
    ),
]
