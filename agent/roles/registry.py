"""Structured role and handoff primitives for multi-agent collaboration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class RoleSpec:
    """A bounded specialist role available to the harness."""

    name: str
    description: str
    responsibilities: list[str]
    allowed_tools: list[str] = field(default_factory=list)
    output_contract: str = "structured_markdown"
    max_context_tokens: int = 16_000
    can_write: bool = False
    can_run_gpu: bool = False
    requires_verification: bool = True


@dataclass
class HandoffPackage:
    """Machine-readable handoff between supervisor and specialist roles."""

    source_role: str
    target_role: str
    task_intent: str
    constraints: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    permissions: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = "medium"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


_ROLES: dict[str, RoleSpec] = {
    "supervisor": RoleSpec(
        name="supervisor",
        description="Plans, delegates, merges specialist outputs, and owns final decisions.",
        responsibilities=[
            "decompose tasks into bounded specialist assignments",
            "route artifacts instead of full conversation history",
            "enforce budgets, approvals, and verification gates",
        ],
        allowed_tools=["plan", "notify"],
        output_contract="handoff_or_final_decision",
        max_context_tokens=24_000,
        can_write=True,
        requires_verification=False,
    ),
    "researcher": RoleSpec(
        name="researcher",
        description="Finds primary sources, structures, datasets, and prior work.",
        responsibilities=[
            "collect source-backed facts",
            "write evidence entries with URLs or artifact paths",
            "avoid design conclusions that are not supported by sources",
        ],
        allowed_tools=[
            "web_search",
            "hf_papers",
            "aidd_bio",
            "hf_docs_fetch",
            "memu_retrieve_memories",
            "memu_memorize_session",
        ],
        output_contract="evidence_table",
        max_context_tokens=16_000,
    ),
    "executor": RoleSpec(
        name="executor",
        description="Runs approved tools and records manifests without broad reasoning.",
        responsibilities=[
            "execute commands exactly within assigned scope",
            "capture stdout, stderr, return codes, and output paths",
            "stop on approval or resource boundaries",
        ],
        allowed_tools=[
            "bash",
            "run_pxdesign",
            "run_boltzgen",
            "run_bindcraft",
            "run_rfd3",
            "memu_retrieve_memories",
            "memu_memorize_session",
        ],
        output_contract="run_manifest",
        max_context_tokens=12_000,
        can_write=True,
        can_run_gpu=True,
    ),
    "verifier": RoleSpec(
        name="verifier",
        description="Independently checks candidate quality against objective gates.",
        responsibilities=[
            "evaluate claims against artifacts and metrics",
            "flag Chai-1/Protenix/Foldseek disagreement",
            "reject reward-hacked or unsupported conclusions",
        ],
        allowed_tools=["aidd_bio", "protein_design_ace_playbook"],
        output_contract="verification_report",
        max_context_tokens=16_000,
        requires_verification=False,
    ),
    "reviewer": RoleSpec(
        name="reviewer",
        description="Finds bugs, missing evidence, unsafe assumptions, and weak tests.",
        responsibilities=[
            "prioritize correctness and safety issues",
            "check whether claims are supported by artifacts",
            "recommend focused follow-up tests",
        ],
        allowed_tools=["read", "bash"],
        output_contract="findings_first_review",
        max_context_tokens=16_000,
        requires_verification=False,
    ),
}


def register_roles(roles: list[RoleSpec]) -> None:
    """Register or replace role specs."""
    for role in roles:
        _ROLES[role.name] = role


def list_roles() -> list[RoleSpec]:
    return [role for _, role in sorted(_ROLES.items())]


def get_role(name: str) -> RoleSpec:
    try:
        return _ROLES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown role: {name}") from exc


def create_handoff(
    *,
    source_role: str,
    target_role: str,
    task_intent: str,
    constraints: list[str] | None = None,
    artifacts: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    open_questions: list[str] | None = None,
    budget: dict[str, Any] | None = None,
    risk_level: RiskLevel = "medium",
) -> HandoffPackage:
    """Create a handoff package with target-role permission defaults."""
    source = get_role(source_role)
    target = get_role(target_role)
    return HandoffPackage(
        source_role=source.name,
        target_role=target.name,
        task_intent=task_intent,
        constraints=constraints or [],
        artifacts=artifacts or [],
        evidence=evidence or [],
        open_questions=open_questions or [],
        permissions={
            "can_write": target.can_write,
            "can_run_gpu": target.can_run_gpu,
            "allowed_tools": target.allowed_tools,
            "requires_verification": target.requires_verification,
        },
        budget=budget or {"max_context_tokens": target.max_context_tokens},
        risk_level=risk_level,
    )
