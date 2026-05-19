"""ACE playbook utilities for protein-design context adaptation.

The implementation follows the ACE pattern of structured bullets plus
incremental delta updates. It keeps curation deterministic so the agent never
rewrites the accumulated context monolithically.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PLAYBOOK_SCHEMA_VERSION = 1
DEFAULT_SECTIONS = [
    "target_analysis",
    "generation_dispatch",
    "validation",
    "failure_modes",
    "harness_feedback",
    "reporting",
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_path(raw: str | None) -> Path:
    if not raw:
        raise ValueError("playbook_path is required")
    return Path(raw).expanduser().resolve()


def _normalize_text(text: str) -> str:
    lowered = text.strip().lower()
    return re.sub(r"\s+", " ", lowered)


def _content_hash(section: str, content: str) -> str:
    digest = hashlib.sha256(
        f"{section}\0{_normalize_text(content)}".encode()
    ).hexdigest()
    return digest[:12]


def _empty_playbook() -> dict[str, Any]:
    return {
        "schema_version": PLAYBOOK_SCHEMA_VERSION,
        "created_at": _now(),
        "updated_at": _now(),
        "sections": {section: [] for section in DEFAULT_SECTIONS},
    }


def load_playbook(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_playbook()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("schema_version", PLAYBOOK_SCHEMA_VERSION)
    data.setdefault("created_at", _now())
    data.setdefault("updated_at", _now())
    data.setdefault("sections", {})
    for section in DEFAULT_SECTIONS:
        data["sections"].setdefault(section, [])
    return data


def save_playbook(path: Path, playbook: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    playbook["updated_at"] = _now()
    path.write_text(
        json.dumps(playbook, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _coerce_delta_items(delta_items: Any) -> list[dict[str, Any]]:
    if isinstance(delta_items, str):
        delta_items = json.loads(delta_items)
    if not isinstance(delta_items, list):
        raise ValueError("delta_items must be a list or JSON list")
    coerced: list[dict[str, Any]] = []
    for item in delta_items:
        if not isinstance(item, dict):
            raise ValueError("each delta item must be an object")
        section = str(item.get("section") or "failure_modes")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if section not in DEFAULT_SECTIONS:
            section = "failure_modes"
        coerced.append(
            {
                "section": section,
                "content": content,
                "source": item.get("source") or "reflector",
                "feedback": item.get("feedback") or "neutral",
                "evidence": item.get("evidence") or {},
            }
        )
    return coerced


def reflect_run_feedback(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert execution feedback into deterministic ACE delta bullets."""
    tool_name = str(arguments.get("tool_name") or arguments.get("source") or "run")
    status = str(arguments.get("status") or "").lower()
    stderr = str(arguments.get("stderr") or "")
    stdout = str(arguments.get("stdout") or "")
    metrics = arguments.get("metrics") or {}
    evidence = {
        "tool": tool_name,
        "status": status,
        "stderr_preview": stderr[:500],
        "stdout_preview": stdout[:500],
        "metrics": metrics,
    }
    combined_log = f"{stdout}\n{stderr}".lower()
    delta_items: list[dict[str, Any]] = []

    if any(token in combined_log for token in ("cuda out of memory", "outofmemory")):
        delta_items.append(
            {
                "section": "failure_modes",
                "content": (
                    f"When {tool_name} hits CUDA OOM, reduce samples or iterations, "
                    "prefer mixed precision, and retry only after recording the GPU budget."
                ),
                "feedback": "helpful",
                "source": tool_name,
                "evidence": evidence,
            }
        )
    if any(token in combined_log for token in ("no such file", "not found", "missing")):
        delta_items.append(
            {
                "section": "target_analysis",
                "content": (
                    "Before generation, verify target structure paths, biological assembly, "
                    "and chain identifiers exist in the execution environment."
                ),
                "feedback": "helpful",
                "source": tool_name,
                "evidence": evidence,
            }
        )

    iptm = _as_float(metrics.get("iptm"))
    plddt = _as_float(metrics.get("plddt"))
    ipae = _as_float(metrics.get("ipae"))
    if iptm is not None or plddt is not None or ipae is not None:
        if (iptm is not None and iptm < 0.75) or (ipae is not None and ipae > 8):
            delta_items.append(
                {
                    "section": "validation",
                    "content": (
                        "Do not advance candidates with weak interface confidence; "
                        "use orthogonal prediction plus interface inspection before spending more compute."
                    ),
                    "feedback": "helpful",
                    "source": tool_name,
                    "evidence": evidence,
                }
            )
        elif (iptm is None or iptm >= 0.8) and (plddt is None or plddt >= 80):
            delta_items.append(
                {
                    "section": "validation",
                    "content": (
                        "Candidates passing ipTM/pLDDT triage still require diversity clustering "
                        "and developability checks before wet-lab handoff."
                    ),
                    "feedback": "helpful",
                    "source": tool_name,
                    "evidence": evidence,
                }
            )

    if status in {"success", "completed", "passed"}:
        delta_items.append(
            {
                "section": "harness_feedback",
                "content": (
                    f"{tool_name} completed successfully; preserve runtime parameters, "
                    "outputs, and validator versions in the campaign trace for regression comparison."
                ),
                "feedback": "helpful",
                "source": tool_name,
                "evidence": evidence,
            }
        )
    elif status in {"failed", "error", "timeout"}:
        delta_items.append(
            {
                "section": "harness_feedback",
                "content": (
                    f"{tool_name} failed; classify the failure before retrying so repeated "
                    "episodes improve the playbook instead of only consuming more compute."
                ),
                "feedback": "helpful",
                "source": tool_name,
                "evidence": evidence,
            }
        )

    if not delta_items:
        delta_items.append(
            {
                "section": "harness_feedback",
                "content": (
                    f"Record {tool_name} execution feedback even when no known failure "
                    "pattern is detected, because sparse traces reduce later attribution quality."
                ),
                "feedback": "neutral",
                "source": tool_name,
                "evidence": evidence,
            }
        )
    return delta_items


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_delta(
    playbook: dict[str, Any],
    delta_items: list[dict[str, Any]],
    *,
    prune_threshold: int = 80,
) -> dict[str, Any]:
    """Merge ACE delta bullets with deterministic grow-and-refine."""
    added = 0
    updated = 0
    for item in delta_items:
        section = item["section"]
        bullet_id = item.get("id") or _content_hash(section, item["content"])
        bullets = playbook["sections"].setdefault(section, [])
        existing = next(
            (bullet for bullet in bullets if bullet["id"] == bullet_id), None
        )
        if existing:
            existing["content"] = item["content"]
            existing["updated_at"] = _now()
            existing["source"] = item["source"]
            existing.setdefault("evidence", []).append(item.get("evidence") or {})
            updated += 1
        else:
            bullets.append(
                {
                    "id": bullet_id,
                    "content": item["content"],
                    "source": item["source"],
                    "helpful_count": 0,
                    "harmful_count": 0,
                    "evidence": [item.get("evidence") or {}],
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )
            added += 1

        target = existing or bullets[-1]
        feedback = str(item.get("feedback") or "neutral").lower()
        if feedback == "helpful":
            target["helpful_count"] = int(target.get("helpful_count") or 0) + 1
        elif feedback == "harmful":
            target["harmful_count"] = int(target.get("harmful_count") or 0) + 1

    removed = refine_playbook(playbook, prune_threshold=prune_threshold)
    return {"added": added, "updated": updated, "removed": removed}


def refine_playbook(playbook: dict[str, Any], *, prune_threshold: int = 80) -> int:
    """De-duplicate by normalized content and prune low-value overflow bullets."""
    removed = 0
    for section, bullets in playbook["sections"].items():
        seen: dict[str, dict[str, Any]] = {}
        refined: list[dict[str, Any]] = []
        for bullet in bullets:
            key = _normalize_text(str(bullet.get("content") or ""))
            duplicate = seen.get(key)
            if duplicate:
                duplicate["helpful_count"] = int(
                    duplicate.get("helpful_count") or 0
                ) + int(bullet.get("helpful_count") or 0)
                duplicate["harmful_count"] = int(
                    duplicate.get("harmful_count") or 0
                ) + int(bullet.get("harmful_count") or 0)
                duplicate.setdefault("evidence", []).extend(
                    bullet.get("evidence") or []
                )
                removed += 1
                continue
            seen[key] = bullet
            refined.append(bullet)

        if len(refined) > prune_threshold:
            refined.sort(
                key=lambda item: (
                    int(item.get("helpful_count") or 0)
                    - int(item.get("harmful_count") or 0),
                    item.get("updated_at") or "",
                ),
                reverse=True,
            )
            removed += len(refined) - prune_threshold
            refined = refined[:prune_threshold]
        playbook["sections"][section] = refined
    return removed


def render_playbook(playbook: dict[str, Any]) -> str:
    """Render a playbook as structured context bullets for an agent prompt."""
    lines = ["# Protein Design ACE Playbook"]
    for section in DEFAULT_SECTIONS:
        lines.append(f"\n## {section.replace('_', ' ').title()}")
        for bullet in playbook["sections"].get(section, []):
            lines.append(
                "- "
                f"[{bullet['id']} h={bullet.get('helpful_count', 0)} "
                f"x={bullet.get('harmful_count', 0)}] {bullet['content']}"
            )
    return "\n".join(lines).strip() + "\n"


def _format_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


ACE_PLAYBOOK_TOOL_SPEC = {
    "name": "protein_design_ace_playbook",
    "description": (
        "Maintain an ACE-style evolving playbook for protein binder design. "
        "Use it to merge execution feedback from generation and validation into "
        "structured incremental context bullets."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["initialize", "apply_delta", "reflect_run", "render"],
            },
            "playbook_path": {
                "type": "string",
                "description": "JSON file where the ACE playbook is stored.",
            },
            "delta_items": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "Incremental bullets with section, content, feedback, source, and evidence."
                ),
            },
            "prune_threshold": {
                "type": "integer",
                "default": 80,
                "description": "Maximum bullets retained per section after refinement.",
            },
            "tool_name": {
                "type": "string",
                "description": "Tool name for reflect_run feedback.",
            },
            "status": {
                "type": "string",
                "description": "Execution status for reflect_run, e.g. success, failed, timeout.",
            },
            "stdout": {
                "type": "string",
                "description": "Bounded stdout/log text for reflect_run.",
            },
            "stderr": {
                "type": "string",
                "description": "Bounded stderr/log text for reflect_run.",
            },
            "metrics": {
                "type": "object",
                "description": "Validation or generation metrics for reflect_run.",
            },
        },
        "required": ["operation", "playbook_path"],
    },
}


async def ace_playbook_handler(arguments: dict[str, Any]) -> tuple[str, bool]:
    try:
        operation = arguments.get("operation")
        path = _safe_path(arguments.get("playbook_path"))
        prune_threshold = int(arguments.get("prune_threshold") or 80)
        playbook = load_playbook(path)

        if operation == "initialize":
            save_playbook(path, playbook)
            return _format_result({"status": "initialized", "path": str(path)}), True

        if operation == "apply_delta":
            delta_items = _coerce_delta_items(arguments.get("delta_items") or [])
            stats = apply_delta(playbook, delta_items, prune_threshold=prune_threshold)
            save_playbook(path, playbook)
            return (
                _format_result(
                    {
                        "status": "updated",
                        "path": str(path),
                        "delta_count": len(delta_items),
                        **stats,
                    }
                ),
                True,
            )

        if operation == "reflect_run":
            delta_items = reflect_run_feedback(arguments)
            stats = apply_delta(playbook, delta_items, prune_threshold=prune_threshold)
            save_playbook(path, playbook)
            return (
                _format_result(
                    {
                        "status": "reflected",
                        "path": str(path),
                        "delta_count": len(delta_items),
                        "delta_items": delta_items,
                        **stats,
                    }
                ),
                True,
            )

        if operation == "render":
            return render_playbook(playbook), True

        return (
            _format_result(
                {
                    "status": "error",
                    "message": "Unknown operation. Use initialize, apply_delta, reflect_run, or render.",
                }
            ),
            False,
        )
    except Exception as exc:
        return _format_result({"status": "error", "message": str(exc)}), False
