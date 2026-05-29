"""Binder design workflow utilities.

This tool is intentionally small and local. It gives the agent a stable
workflow surface for binder-design projects independent of which generator
produced the files (BindCraft, BoltzGen, PXDesign, or a later MCP).
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


METRIC_ALIASES = {
    "name": [
        "name",
        "design",
        "design_name",
        "binder",
        "binder_name",
        "model",
        "description",
    ],
    "plddt": ["plddt", "average_plddt", "avg_plddt", "mean_plddt"],
    "iptm": [
        "iptm",
        "ipTM",
        "i_pTM",
        "average_i_pTM",
        "average_iptm",
        "interface_ptm",
    ],
    "ipae": ["ipae", "average_i_pae", "average_ipae", "i_pae", "pae_interaction"],
    "pae": ["pae", "average_pae", "mean_pae"],
    "interface_score": [
        "interface_score",
        "interface_energy",
        "interface_delta_g",
        "interface_dg",
        "average_dg",
        "average_dG",
        "interface_sc",
        "ddg",
        "delta_g",
    ],
    "binder_score": ["binder_score", "score", "quality_score", "confidence_score"],
    "clashes": [
        "clashes",
        "num_clashes",
        "clash_count",
        "average_relaxed_clashes",
        "relaxed_clashes",
        "average_unrelaxed_clashes",
    ],
    "rmsd": [
        "rmsd",
        "backbone_rmsd",
        "bb_rmsd",
        "average_binder_rmsd",
        "binder_rmsd",
        "average_hotspot_rmsd",
    ],
    "interface_contacts": [
        "interface_contacts",
        "contacts",
        "num_contacts",
        "n_interfaceresidues",
        "average_n_interfaceresidues",
    ],
    "interface_hbonds": [
        "interface_hbonds",
        "hbonds",
        "hbond_count",
        "n_interfacehbonds",
        "average_n_interfacehbonds",
    ],
    "buried_sasa": [
        "buried_sasa",
        "bsa",
        "interface_area",
        "buried_surface_area",
        "dsasa",
        "average_dsasa",
    ],
    "hydrophobic_sasa": [
        "hydrophobic_sasa",
        "interface_hydrophobic_sasa",
        "hydrophobic_surface",
        "interface_hydrophobicity",
        "average_interface_hydrophobicity",
        "surface_hydrophobicity",
        "average_surface_hydrophobicity",
    ],
    "aggregation_score": [
        "aggregation_score",
        "agg_score",
        "developability_aggregation",
    ],
    "sequence": ["sequence", "binder_sequence", "seq"],
    "structure_path": ["structure_path", "pdb", "pdb_path", "cif", "cif_path"],
    "validation_source": ["validation_source", "validator", "model_source", "engine"],
    "fold_cluster": ["fold_cluster", "cluster", "foldseek_cluster", "tm_cluster"],
}

HIGH_IS_BETTER = {
    "plddt",
    "iptm",
    "binder_score",
    "interface_contacts",
    "interface_hbonds",
    "buried_sasa",
}
LOW_IS_BETTER = {
    "ipae",
    "pae",
    "interface_score",
    "clashes",
    "rmsd",
    "hydrophobic_sasa",
    "aggregation_score",
}

DEFAULT_FILTERS = {
    "plddt": 80,
    "iptm": 0.75,
    "ipae": 8,
    "clashes": 0,
    "rmsd": 3,
}

STRICT_FILTERS = {
    "plddt": 85,
    "iptm": 0.8,
    "ipae": 5,
    "clashes": 0,
    "rmsd": 2.5,
}

CAMPAIGN_STAGES = [
    "intake target, indication, binder modality, epitope constraints, and no-go regions",
    "collect target records from UniProt, RCSB, AlphaFold DB, papers, and known binder structures",
    "profile the target surface for chain state, cofactors/PTMs, glycosylation, membrane context, and flexible/disordered regions",
    "choose generation engines and sampling budget from target difficulty and required constraints",
    "run de novo generation behind MCP/subprocess boundaries",
    "cross-validate candidates with at least one orthogonal structure predictor before escalation",
    "cluster validated binders by fold or interface geometry and keep diverse representatives",
    "write a final binder dossier with evidence, risks, and wet-lab handoff notes",
    "promote repeated workflow patterns into a reusable skill card for the next campaign",
]


def _safe_path(raw: str | None) -> Path:
    if not raw:
        raise ValueError("path is required")
    return Path(raw).expanduser().resolve()


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_value(row: dict[str, Any], aliases: list[str]) -> Any:
    lower_map = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in aliases:
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    return None


def _normalize_row(
    row: dict[str, Any], source_file: Path, index: int
) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "source_file": str(source_file),
        "source_row": index,
    }
    for metric, aliases in METRIC_ALIASES.items():
        value = _find_value(row, aliases)
        if metric in HIGH_IS_BETTER or metric in LOW_IS_BETTER:
            normalized[metric] = _as_float(value)
        elif value not in (None, ""):
            normalized[metric] = str(value)

    if "name" not in normalized:
        normalized["name"] = f"{source_file.stem}:{index}"
    return normalized


def _discover_metric_files(root: Path) -> list[Path]:
    patterns = [
        "*final*design*stats*.csv",
        "*design*stats*.csv",
        "*metrics*.csv",
        "*scores*.csv",
        "*.csv",
    ]
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                files.append(path)
    return files


def _scan_for_oom_or_failures(root: Path) -> dict[str, Any]:
    import re

    oom_pattern = re.compile(
        r"(cuda out of memory|out-of-memory|oom|cublas.*alloc|cudnn.*alloc)",
        re.IGNORECASE,
    )
    timeout_pattern = re.compile(
        r"(timed out|timeout|time limit exceeded)", re.IGNORECASE
    )
    status = {"oom": False, "timeout": False, "details": None}
    if not root.exists():
        return status
    for log_file in sorted(root.rglob("*.log")):
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
            if oom_pattern.search(content):
                status["oom"] = True
                status["details"] = (
                    f"Detected CUDA Out Of Memory in log: {log_file.name}"
                )
                return status
            if timeout_pattern.search(content):
                status["timeout"] = True
                status["details"] = (
                    f"Detected execution Timeout in log: {log_file.name}"
                )
                return status
        except Exception:
            continue
    for err_file in sorted(root.rglob("*.txt")):
        try:
            content = err_file.read_text(encoding="utf-8", errors="replace")
            if oom_pattern.search(content):
                status["oom"] = True
                status["details"] = (
                    f"Detected CUDA Out Of Memory in text file: {err_file.name}"
                )
                return status
        except Exception:
            continue
    return status


def _read_candidates(
    root: Path, metric_files: list[str] | None = None
) -> list[dict[str, Any]]:
    files = (
        [_safe_path(path) for path in metric_files]
        if metric_files
        else _discover_metric_files(root)
    )
    candidates: list[dict[str, Any]] = []
    for file_path in files:
        if not file_path.exists() or file_path.suffix.lower() != ".csv":
            continue
        with file_path.open(
            "r", encoding="utf-8", errors="replace", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                candidates.append(_normalize_row(row, file_path, index))
    return candidates


def _score_candidate(candidate: dict[str, Any]) -> float:
    score = 0.0
    plddt = candidate.get("plddt")
    if plddt is not None:
        score += plddt / 100.0
    iptm = candidate.get("iptm")
    if iptm is not None:
        score += iptm
    binder_score = candidate.get("binder_score")
    if binder_score is not None:
        score += binder_score / 10.0

    ipae = candidate.get("ipae")
    if ipae is not None:
        score -= ipae / 10.0
    pae = candidate.get("pae")
    if pae is not None:
        score -= pae / 20.0
    rmsd = candidate.get("rmsd")
    if rmsd is not None:
        score -= rmsd / 5.0
    clashes = candidate.get("clashes")
    if clashes is not None:
        score -= clashes / 10.0
    interface_score = candidate.get("interface_score")
    if interface_score is not None:
        # Negative interface energies are favorable.
        score += -interface_score / 50.0
    interface_contacts = candidate.get("interface_contacts")
    if interface_contacts is not None:
        score += interface_contacts / 50.0
    interface_hbonds = candidate.get("interface_hbonds")
    if interface_hbonds is not None:
        score += interface_hbonds / 10.0
    buried_sasa = candidate.get("buried_sasa")
    if buried_sasa is not None:
        score += buried_sasa / 2000.0
    hydrophobic_sasa = candidate.get("hydrophobic_sasa")
    if hydrophobic_sasa is not None:
        score -= hydrophobic_sasa / 2500.0
    aggregation_score = candidate.get("aggregation_score")
    if aggregation_score is not None:
        score -= aggregation_score / 10.0
    return round(score, 4)


def _passes_filters(
    candidate: dict[str, Any], filters: dict[str, Any]
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for key, threshold in filters.items():
        value = candidate.get(key)
        numeric_threshold = _as_float(threshold)
        if numeric_threshold is None or value is None:
            continue
        if key in HIGH_IS_BETTER and value < numeric_threshold:
            failures.append(f"{key}={value} < {numeric_threshold}")
        elif key in LOW_IS_BETTER and value > numeric_threshold:
            failures.append(f"{key}={value} > {numeric_threshold}")
    return not failures, failures


def _difficulty(requirements: dict[str, Any]) -> str:
    score = 0
    for key in ("epitope", "hotspots", "no_go_regions", "excluded_regions"):
        if requirements.get(key):
            score += 1
    for key in ("glycosylation", "membrane_context", "oligomeric_state", "ptms"):
        if requirements.get(key):
            score += 1
    if requirements.get("species_cross_reactivity"):
        score += 1
    if requirements.get("binder_length"):
        length = str(requirements["binder_length"])
        if any(token in length for token in ("<", ">", "-")):
            score += 1
    if score >= 4:
        return "hard"
    if score >= 2:
        return "moderate"
    return "standard"


def _campaign_modality(requirements: dict[str, Any]) -> str:
    """Identify the campaign type (modality) matching the Latent-Y architecture."""
    if (
        requirements.get("publication")
        or requirements.get("paper")
        or requirements.get("doi")
    ):
        return "design_from_publication"
    if requirements.get("species_cross_reactivity") or requirements.get(
        "cross_species"
    ):
        return "cross_species_design"
    if (
        requirements.get("epitope")
        or requirements.get("functional_blockade")
        or requirements.get("indication")
    ):
        return "epitope_discovery"
    return "standard_design"


def _hitl_steering_options(requirements: dict[str, Any]) -> list[dict[str, Any]]:
    """Generates strategic design options for Human-in-the-Loop (HITL) steering, modeled after Latent-Y."""
    options = []
    modality = _campaign_modality(requirements)

    if modality == "design_from_publication":
        options.append(
            {
                "option_id": "publication_direct_extract",
                "name": "Auto-Extract from Scientific Paper",
                "gpu_cost": "low",
                "success_probability": "85%",
                "pros": "Highly autonomous; directly parses published hotspot constraints and active residue IDs.",
                "cons": "Highly dependent on OCR accuracy and target UniProt residue numbering consistency.",
                "steering_command": "Run direct extraction on the provided literature to auto-fill binder hotspots.",
            }
        )
        options.append(
            {
                "option_id": "publication_manual_hotspot",
                "name": "Hybrid Alignment & Manual Hotspot Input",
                "gpu_cost": "low",
                "success_probability": "95%",
                "pros": "Guarantees highly precise docking vector and eliminates any numbering drift.",
                "cons": "Requires the researcher to verify residue indexes in PyMOL first.",
                "steering_command": "Use the paper for biological context, but override hotspots manually with residues: [list].",
            }
        )
    elif modality == "cross_species_design":
        options.append(
            {
                "option_id": "cross_species_conserved_only",
                "name": "Conserved Epitope Targeting Only",
                "gpu_cost": "moderate",
                "success_probability": "70%",
                "pros": "Designs bind both orthologs with identical geometric binding mode.",
                "cons": "Limits sampling search space to highly conserved target surface blocks.",
                "steering_command": "Filter all hotspots to only residues sharing 100% homology across target species.",
            }
        )
        options.append(
            {
                "option_id": "cross_species_dual_optimization",
                "name": "Dual-Homolog Co-evolution (BindCraft)",
                "gpu_cost": "high",
                "success_probability": "90%",
                "pros": "Achieves high affinity designs by co-optimizing and folding binders against both species structures.",
                "cons": "Increases AlphaFold recycling time and compute costs by 2.5x.",
                "steering_command": "Run BindCraft campaign co-evolving the binder against both Human and Cyno PDB structures.",
            }
        )
    else:  # epitope_discovery or standard_design
        options.append(
            {
                "option_id": "epitope_boltzgen_constraint",
                "name": "Microenvironment Constrained Sampling (BoltzGen)",
                "gpu_cost": "moderate",
                "success_probability": "80%",
                "pros": "Extremely fast generation localized specifically to the functional binding pocket.",
                "cons": "May miss novel highly-stable folding topologies outside the constraint box.",
                "steering_command": "Constrain generation to pocket residues using BoltzGen with force-field boundary calibration.",
            }
        )
        options.append(
            {
                "option_id": "epitope_rfd3_de_novo",
                "name": "Atom-Level complementary All-Atom Sampling (RFD3)",
                "gpu_cost": "high",
                "success_probability": "85%",
                "pros": "Designs novel highly-stable folding topologies with robust physical complementarity.",
                "cons": "Requires longer post-generation screening and orthogonal AlphaFold filtering batches.",
                "steering_command": "Execute RFD3 all-atom de novo campaign targeting the functional surface.",
            }
        )

    return options


def _risk_register(requirements: dict[str, Any]) -> list[dict[str, str]]:
    risks = [
        {
            "risk": "single-model reward hacking",
            "mitigation": "Require orthogonal Chai-1/Protenix/AF-style validation before shortlisting.",
        },
        {
            "risk": "false-positive interface confidence",
            "mitigation": "Review interface PAE, contacts, buried area, clashes, and approach vector, not only pLDDT.",
        },
    ]
    if requirements.get("glycosylation") or requirements.get("ptms"):
        risks.append(
            {
                "risk": "PTM or glycan shielding blocks the designed approach vector",
                "mitigation": "Validate against representative modified target models and reject steric collisions.",
            }
        )
    if requirements.get("membrane_context"):
        risks.append(
            {
                "risk": "binder binds purified ectodomain but fails in cell-surface geometry",
                "mitigation": "Filter designs by membrane-side accessibility and orientation.",
            }
        )
    if requirements.get("species_cross_reactivity"):
        risks.append(
            {
                "risk": "candidate loses cross-species binding at non-conserved hotspot residues",
                "mitigation": "Align ortholog structures/sequences and avoid species-variable anchor residues.",
            }
        )
    if requirements.get("no_go_regions") or requirements.get("excluded_regions"):
        risks.append(
            {
                "risk": "design drifts into a forbidden epitope during optimization",
                "mitigation": "Carry no-go residue masks into generation and final structural inspection.",
            }
        )
    return risks


def _tool_strategy(requirements: dict[str, Any]) -> list[dict[str, str]]:
    difficulty = _difficulty(requirements)
    strategy = [
        {
            "tool": "aidd_bio",
            "use": "retrieve target structures, sequences, known complexes, PTM notes, and structural homologs",
        }
    ]
    if requirements.get("epitope") or requirements.get("hotspots"):
        strategy.append(
            {
                "tool": "BoltzGen",
                "use": "constraint-conditioned generation around specified hotspot or epitope geometry",
            }
        )
    if difficulty in {"standard", "moderate", "hard"}:
        strategy.append(
            {
                "tool": "PXDesign",
                "use": "high-throughput backbone and sequence exploration for diverse starting binders",
            }
        )
    if difficulty in {"moderate", "hard"}:
        strategy.append(
            {
                "tool": "BindCraft",
                "use": "iterative refinement and side-chain/interface optimization of promising sites",
            }
        )
    strategy.extend(
        [
            {
                "tool": "Chai-1 or Protenix",
                "use": "orthogonal complex prediction and confidence filtering",
            },
            {
                "tool": "Foldseek or TM-align",
                "use": "fold/interface clustering to keep diverse representatives",
            },
        ]
    )
    return strategy


def _acceptance_criteria(strict: bool = False) -> dict[str, Any]:
    filters = STRICT_FILTERS if strict else DEFAULT_FILTERS
    return {
        "primary_filters": filters,
        "orthogonal_validation": "shortlisted candidates need support from a second structure predictor or independent scoring source",
        "diversity": "select at most one representative per fold_cluster unless a cluster contains clearly distinct interfaces",
        "manual_review": [
            "inspect target PTMs/glycans/membrane orientation",
            "check no-go epitope and approach-vector constraints",
            "confirm sequence developability and aggregation risk before wet-lab handoff",
        ],
    }


def _campaign_plan(requirements: dict[str, Any]) -> dict[str, Any]:
    strict = bool(requirements.get("strict_validation"))
    return {
        "difficulty": _difficulty(requirements),
        "campaign_modality": _campaign_modality(requirements),
        "stages": CAMPAIGN_STAGES,
        "tool_strategy": _tool_strategy(requirements),
        "acceptance_criteria": _acceptance_criteria(strict),
        "risk_register": _risk_register(requirements),
        "hitl_steering_options": _hitl_steering_options(requirements),
        "open_questions": _open_questions(requirements),
    }


def _open_questions(requirements: dict[str, Any]) -> list[str]:
    questions = []
    if not requirements.get("target_chains"):
        questions.append(
            "Which biological assembly and target chain(s) should define the binder interface?"
        )
    if not requirements.get("epitope") and not requirements.get("hotspots"):
        questions.append(
            "Is there a required epitope/hotspot, or should the agent discover candidate binding surfaces?"
        )
    if not requirements.get("binder_length"):
        questions.append(
            "What binder length or scaffold class is acceptable for synthesis and expression?"
        )
    if not requirements.get("assay"):
        questions.append(
            "What downstream assay will define success: SPR/BLI affinity, cell binding, functional blockade, or another readout?"
        )
    return questions


def _validation_tier(candidate: dict[str, Any]) -> str:
    source = str(candidate.get("validation_source", "")).lower()
    if any(token in source for token in ("chai", "protenix", "af", "alphafold")):
        return "orthogonal"
    if any(
        token in source for token in ("generator", "bindcraft", "pxdesign", "boltzgen")
    ):
        return "generator_score_only"
    if candidate.get("iptm") is not None or candidate.get("ipae") is not None:
        return "structure_confidence"
    return "generator_score_only"


def _decision(candidate: dict[str, Any], failures: list[str]) -> str:
    if failures:
        return "reject"
    tier = _validation_tier(candidate)
    if tier == "generator_score_only":
        return "hold_for_orthogonal_validation"
    return "advance"


def _next_actions(candidate: dict[str, Any], failures: list[str]) -> list[str]:
    if failures:
        return ["repair or discard: " + "; ".join(failures)]
    actions = []
    if _validation_tier(candidate) == "generator_score_only":
        actions.append("run orthogonal Chai-1/Protenix validation")
    if not candidate.get("fold_cluster"):
        actions.append("cluster with Foldseek or TM-align")
    if candidate.get("hydrophobic_sasa") is None:
        actions.append("compute interface hydrophobicity/developability metrics")
    if not actions:
        actions.append("manual structural review and wet-lab handoff consideration")
    return actions


def _diversity_representatives(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    representatives: dict[str, dict[str, Any]] = {}
    unclustered_index = 0
    for candidate in ranked:
        cluster = candidate.get("fold_cluster")
        if not cluster:
            unclustered_index += 1
            cluster = f"unclustered:{unclustered_index}"
        if cluster not in representatives:
            representatives[str(cluster)] = candidate
    return list(representatives.values())


def _format_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _slugify_skill_name(value: str | None) -> str:
    raw = (value or "binder_campaign").strip().lower()
    slug = []
    for char in raw:
        if char.isalnum():
            slug.append(char)
        elif char in {"-", "_"}:
            slug.append(char)
        elif slug and slug[-1] != "-":
            slug.append("-")
    normalized = "".join(slug).strip("-_")
    return normalized or "binder_campaign"


def _render_bullet_list(items: list[str], *, empty_label: str = "none") -> str:
    if not items:
        return f"- {empty_label}"
    return "\n".join(f"- {item}" for item in items)


def _render_tool_strategy(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- none"
    lines = []
    for item in items:
        tool = str(item.get("tool") or "tool")
        use = str(item.get("use") or "")
        lines.append(f"- {tool}: {use}".rstrip())
    return "\n".join(lines)


def _render_risk_register(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- none"
    lines = []
    for item in items:
        risk = str(item.get("risk") or "risk")
        mitigation = str(item.get("mitigation") or "")
        lines.append(f"- {risk}: {mitigation}".rstrip())
    return "\n".join(lines)


def _render_open_questions(items: list[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def _render_steering_options(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- none"
    lines = []
    for item in items:
        name = str(item.get("name") or "Option")
        prob = str(item.get("success_probability") or "unknown")
        cost = str(item.get("gpu_cost") or "unknown")
        pros = str(item.get("pros") or "")
        cons = str(item.get("cons") or "")
        cmd = str(item.get("steering_command") or "")
        lines.append(
            f"### {name}\n"
            f"- **Success Probability:** {prob}\n"
            f"- **GPU Cost:** {cost}\n"
            f"- **Pros:** {pros}\n"
            f"- **Cons:** {cons}\n"
            f"- **Steering Command:** `{cmd}`\n"
        )
    return "\n".join(lines)


def _render_skill_card(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    skill_name: str,
) -> str:
    campaign_plan = dict(manifest.get("campaign_plan") or {})
    requirements = dict(manifest.get("requirements") or {})
    tool_strategy = list(campaign_plan.get("tool_strategy") or [])
    acceptance_criteria = dict(campaign_plan.get("acceptance_criteria") or {})
    primary_filters = dict(acceptance_criteria.get("primary_filters") or {})
    risk_register = list(campaign_plan.get("risk_register") or [])
    open_questions = list(campaign_plan.get("open_questions") or [])
    steering_options = list(campaign_plan.get("hitl_steering_options") or [])
    workflow = list(manifest.get("workflow") or CAMPAIGN_STAGES)
    tools = list(manifest.get("tools") or [])
    constraints = [
        f"{key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
        for key, value in sorted(requirements.items())
    ]

    description = (
        "Reusable AIDD binder-design workflow distilled from a completed campaign."
    )
    frontmatter = [
        "---",
        f"name: {json.dumps(skill_name)}",
        f"description: {json.dumps(description)}",
        f"workflow: {json.dumps('aidd_binder')}",
        f"source_manifest: {json.dumps(str(manifest_path))}",
        f"created_at: {json.dumps(str(manifest.get('created_at') or ''))}",
        f"target_name: {json.dumps(str(manifest.get('target_name') or ''))}",
        f"target_structure: {json.dumps(str(manifest.get('target_structure') or ''))}",
        "---",
        "",
    ]

    body = [
        f"# {skill_name}",
        "",
        "## When To Use",
        _render_bullet_list(
            [
                "You are starting a new binder campaign against a structured target.",
                "You want to reuse a successful binder workflow instead of reconstructing it from scratch.",
                "You need the same intake, validation, ranking, and handoff pattern on the next project.",
            ]
        ),
        "",
        "## Project Snapshot",
        _render_bullet_list(
            [
                f"Target: {manifest.get('target_name') or 'unknown'}",
                f"Structure: {manifest.get('target_structure') or 'unknown'}",
                f"Campaign difficulty: {campaign_plan.get('difficulty') or 'unknown'}",
                f"Campaign modality: {campaign_plan.get('campaign_modality') or 'unknown'}",
                f"Tools: {', '.join(tools) if tools else 'none'}",
            ]
        ),
        "",
        "## Inputs To Collect",
        _render_bullet_list(
            [
                "target_name",
                "target_structure",
                "target_chains",
                "epitope or hotspots",
                "no-go regions",
                "binder_length",
                "assay",
            ]
        ),
        "",
        "## Constraints Captured",
        _render_bullet_list(constraints),
        "",
        "## Workflow",
        _render_bullet_list([str(step) for step in workflow]),
        "",
        "## Tool Strategy",
        _render_tool_strategy(tool_strategy),
        "",
        "## Acceptance Criteria",
        _render_bullet_list(
            [
                *[
                    f"{key} >= {value}"
                    if key in HIGH_IS_BETTER
                    else f"{key} <= {value}"
                    for key, value in sorted(primary_filters.items())
                ],
                str(
                    acceptance_criteria.get("orthogonal_validation")
                    or "orthogonal validation required"
                ),
                str(
                    acceptance_criteria.get("diversity")
                    or "cluster diverse representatives"
                ),
            ]
        ),
        "",
        "## Risk Register",
        _render_risk_register(risk_register),
        "",
        "## Open Questions",
        _render_open_questions(open_questions),
        "",
        "## Latent-Y HITL Steering Options",
        _render_steering_options(steering_options),
        "",
        "## Historical Notes",
        _render_bullet_list(
            [
                "Keep the skill in sync with the latest manifest and metrics instead of letting it drift from evidence.",
                "Promote repeated successful workflow shapes into this card, then prune dead steps when campaign evidence changes.",
                "Use the project trace and exported skill together so the next run starts from durable context, not raw transcript noise.",
            ]
        ),
        "",
    ]

    return "\n".join(frontmatter + body)


BINDER_DESIGN_TOOL_SPEC = {
    "name": "binder_design",
    "description": (
        "Manage AIDD binder-design projects and rank generated binder candidates. "
        "Use after literature/target validation and after BindCraft, BoltzGen, "
        "PXDesign, or another generator has produced outputs. Can also export a "
        "reusable skill card from a completed campaign."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "plan_campaign",
                    "create_project",
                    "inspect_outputs",
                    "rank_candidates",
                    "optimize_next_round",
                    "export_skill",
                    "setup_tools",
                    "run_diagnostics",
                ],
                "description": "Binder-design workflow operation to run.",
            },
            "project_dir": {
                "type": "string",
                "description": "Project directory for manifests and outputs.",
            },
            "target_name": {
                "type": "string",
                "description": "Target protein name or identifier for create_project.",
            },
            "target_structure": {
                "type": "string",
                "description": "PDB/mmCIF path, PDB ID, AlphaFold accession, or URL.",
            },
            "requirements": {
                "type": "object",
                "description": (
                    "User constraints such as chains, epitope, hotspots, no-go regions, "
                    "binder length, assay, PTMs, glycosylation, membrane context, and species cross-reactivity."
                ),
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Generator/evaluator tools planned for the project.",
            },
            "outputs_dir": {
                "type": "string",
                "description": "Directory containing generator outputs to inspect or rank.",
            },
            "metric_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional explicit CSV metric files to parse.",
            },
            "filters": {
                "type": "object",
                "description": (
                    "Numeric filter thresholds. High-is-better: plddt, iptm, binder_score. "
                    "Low-is-better: ipae, pae, interface_score, clashes, rmsd."
                ),
            },
            "strict_validation": {
                "type": "boolean",
                "description": "Use stricter default acceptance criteria when planning.",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of ranked candidates to return.",
                "default": 10,
            },
            "skill_name": {
                "type": "string",
                "description": "Reusable skill name used when exporting a skill card.",
                "default": "binder_campaign",
            },
            "previous_round_tool": {
                "type": "string",
                "description": "The generator tool used in the previous round.",
            },
            "previous_round_parameters": {
                "type": "object",
                "description": "The parameter settings used in the previous round.",
            },
        },
        "required": ["operation"],
    },
}


async def binder_design_handler(arguments: dict[str, Any]) -> tuple[str, bool]:
    try:
        operation = arguments.get("operation")
        if operation == "plan_campaign":
            requirements = dict(arguments.get("requirements") or {})
            if arguments.get("strict_validation") is not None:
                requirements["strict_validation"] = bool(
                    arguments.get("strict_validation")
                )
            return (
                _format_result(
                    {
                        "status": "planned",
                        "target_name": arguments.get("target_name"),
                        "target_structure": arguments.get("target_structure"),
                        "campaign_plan": _campaign_plan(requirements),
                    }
                ),
                True,
            )

        if operation == "create_project":
            project_dir = _safe_path(arguments.get("project_dir"))
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "skills").mkdir(exist_ok=True)
            requirements = arguments.get("requirements") or {}
            manifest = {
                "created_at": datetime.now(UTC).isoformat(),
                "target_name": arguments.get("target_name"),
                "target_structure": arguments.get("target_structure"),
                "requirements": requirements,
                "tools": arguments.get("tools")
                or ["aidd_bio", "bindcraft", "boltzgen", "pxdesign"],
                "workflow": CAMPAIGN_STAGES,
                "campaign_plan": _campaign_plan(requirements),
            }
            manifest_path = project_dir / "binder_project.json"
            manifest_path.write_text(_format_result(manifest) + "\n", encoding="utf-8")
            (project_dir / "outputs").mkdir(exist_ok=True)
            return _format_result(
                {"status": "created", "manifest": str(manifest_path)}
            ), True

        if operation == "inspect_outputs":
            root = _safe_path(
                arguments.get("outputs_dir") or arguments.get("project_dir")
            )
            candidates = _read_candidates(root, arguments.get("metric_files"))
            metric_files = sorted(
                {candidate["source_file"] for candidate in candidates}
            )
            return (
                _format_result(
                    {
                        "status": "inspected",
                        "outputs_dir": str(root),
                        "metric_files": metric_files,
                        "candidate_count": len(candidates),
                        "available_metrics": sorted(
                            {
                                key
                                for candidate in candidates
                                for key, value in candidate.items()
                                if value is not None
                            }
                        ),
                    }
                ),
                True,
            )

        if operation == "rank_candidates":
            root = _safe_path(
                arguments.get("outputs_dir") or arguments.get("project_dir")
            )
            top_k = int(arguments.get("top_k") or 10)
            filters = arguments.get("filters") or DEFAULT_FILTERS
            candidates = _read_candidates(root, arguments.get("metric_files"))
            ranked = []
            rejected = []
            for candidate in candidates:
                passed, failures = _passes_filters(candidate, filters)
                candidate = dict(candidate)
                candidate["rank_score"] = _score_candidate(candidate)
                candidate["validation_tier"] = _validation_tier(candidate)
                candidate["decision"] = _decision(candidate, failures)
                candidate["next_actions"] = _next_actions(candidate, failures)
                if passed:
                    ranked.append(candidate)
                else:
                    candidate["filter_failures"] = failures
                    rejected.append(candidate)
            ranked.sort(key=lambda item: item["rank_score"], reverse=True)
            return (
                _format_result(
                    {
                        "status": "ranked",
                        "outputs_dir": str(root),
                        "filters": filters,
                        "candidate_count": len(candidates),
                        "passed_count": len(ranked),
                        "rejected_count": len(rejected),
                        "top_candidates": ranked[:top_k],
                        "diversity_representatives": _diversity_representatives(ranked)[
                            :top_k
                        ],
                    }
                ),
                True,
            )

        if operation == "optimize_next_round":
            root = _safe_path(
                arguments.get("outputs_dir") or arguments.get("project_dir")
            )
            project_dir = None
            if arguments.get("project_dir"):
                try:
                    project_dir = _safe_path(arguments.get("project_dir"))
                except Exception:
                    pass

            manifest = None
            if project_dir and (project_dir / "binder_project.json").exists():
                try:
                    manifest_path = project_dir / "binder_project.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            prev_tool = arguments.get("previous_round_tool")
            if not prev_tool and manifest:
                tools = manifest.get("tools")
                if tools and isinstance(tools, list):
                    prev_tool = tools[0]
            if not prev_tool:
                path_str = str(root).lower()
                if "bindcraft" in path_str:
                    prev_tool = "bindcraft"
                elif "boltzgen" in path_str:
                    prev_tool = "boltzgen"
                elif "pxdesign" in path_str:
                    prev_tool = "pxdesign"
                else:
                    prev_tool = "pxdesign"

            prev_params = arguments.get("previous_round_parameters") or {}
            if manifest and not prev_params:
                prev_params = manifest.get("requirements") or {}

            candidates = _read_candidates(root, arguments.get("metric_files"))

            status_summary = "unknown"
            next_tool = prev_tool
            next_params = dict(prev_params)
            rationale = ""

            candidate_count = len(candidates)

            if candidate_count == 0:
                failure_info = _scan_for_oom_or_failures(root)
                if failure_info["oom"]:
                    status_summary = "failed_hardware_oom"
                    rationale = f"Previous run failed due to GPU resource constraints. {failure_info['details']}."
                    next_params["num_samples"] = max(
                        1, int(prev_params.get("num_samples", 100) // 2)
                    )
                    if "iterations" in next_params:
                        next_params["iterations"] = max(
                            5, int(prev_params.get("iterations", 50) // 2)
                        )
                    next_params["mixed_precision"] = True
                elif failure_info["timeout"]:
                    status_summary = "failed_timeout"
                    rationale = f"Previous run timed out. {failure_info['details']}. Switching to a faster, lighter backend."
                    if prev_tool == "bindcraft":
                        next_tool = "pxdesign"
                        next_params["num_samples"] = 50
                    else:
                        next_params["num_samples"] = max(
                            10, int(prev_params.get("num_samples", 100) // 2)
                        )
                else:
                    status_summary = "failed_execution_error"
                    rationale = "No design candidates or metric files were discovered, and no explicit OOM or Timeout logs were detected. This indicates an execution setup failure. Recommending tool verification and standard PXdesign fallback."
                    next_tool = "pxdesign"
                    next_params["num_samples"] = 20
            else:
                iptms = [c["iptm"] for c in candidates if c.get("iptm") is not None]
                plddts = [c["plddt"] for c in candidates if c.get("plddt") is not None]
                clashes_list = [
                    c["clashes"] for c in candidates if c.get("clashes") is not None
                ]
                rmsds = [c["rmsd"] for c in candidates if c.get("rmsd") is not None]
                sasas = [
                    c["buried_sasa"]
                    for c in candidates
                    if c.get("buried_sasa") is not None
                ]
                contacts_list = [
                    c["interface_contacts"]
                    for c in candidates
                    if c.get("interface_contacts") is not None
                ]

                max_iptm = max(iptms) if iptms else 0.0
                mean_iptm = sum(iptms) / len(iptms) if iptms else 0.0
                max_plddt = max(plddts) if plddts else 0.0
                mean_plddt = sum(plddts) / len(plddts) if plddts else 0.0
                mean_clashes = (
                    sum(clashes_list) / len(clashes_list) if clashes_list else 0.0
                )
                mean_rmsd = sum(rmsds) / len(rmsds) if rmsds else 0.0
                mean_sasa = sum(sasas) / len(sasas) if sasas else 0.0
                mean_contacts = (
                    sum(contacts_list) / len(contacts_list) if contacts_list else 0.0
                )

                filters = arguments.get("filters") or DEFAULT_FILTERS
                passed_count = sum(
                    1 for c in candidates if _passes_filters(c, filters)[0]
                )

                if passed_count > 0 and max_iptm >= 0.85:
                    status_summary = "success_escalate_or_scale"
                    if prev_tool in ("pxdesign", "rfd3", "boltzgen"):
                        next_tool = "bindcraft"
                        rationale = (
                            f"Outstanding results! We found {passed_count} validated candidates passing filters, "
                            f"with a maximum interface confidence (ipTM) of {max_iptm:.2f} and high pLDDT ({max_plddt:.1f}). "
                            f"Escalating the design campaign to BindCraft for deep multi-round structural refinement "
                            "and PyRosetta interface minimization to secure wet-lab grade candidates."
                        )
                        next_params["iterations"] = 50
                        next_params["num_designs"] = 5
                    else:
                        next_tool = "bindcraft"
                        rationale = (
                            f"Outstanding BindCraft results! {passed_count} candidates passed strict filters with max ipTM = {max_iptm:.2f}. "
                            "Recommending staying with BindCraft to run a larger design pool (increasing target designs/trajectories) "
                            "and running Foldseek clustering for wet-lab representative selection."
                        )
                        next_params["num_designs"] = int(
                            prev_params.get("num_designs", 1) + 2
                        )

                elif passed_count > 0 and max_iptm >= 0.75:
                    status_summary = "moderate_success_local_search"
                    next_tool = prev_tool
                    rationale = (
                        f"Moderate campaign success. {passed_count} candidates passed filters, with a solid max ipTM of {max_iptm:.2f}. "
                        "Staying with the current tool but executing a fine-grained local search. "
                        "Adjusting binder length and hotspot focus to improve affinity."
                    )
                    length = int(
                        _as_float(prev_params.get("binder_length", 100)) or 100
                    )
                    next_params["binder_length"] = length + 5

                elif mean_plddt < 70 and plddts:
                    status_summary = "poor_stability_restructure"
                    next_tool = "bindcraft"
                    rationale = (
                        f"Previous candidates exhibited poor structural stability (mean pLDDT = {mean_plddt:.1f} < 70). "
                        "Switching generator to BindCraft, which enforces strict structural folding, secondary structure preservation, "
                        "and PyRosetta-based steric energy filters during generation."
                    )
                    next_params["iterations"] = 60

                elif max_iptm < 0.70:
                    status_summary = "poor_interface_switch_tool"
                    if prev_tool in ("pxdesign", "boltzgen"):
                        next_tool = "rfd3"
                        rationale = (
                            f"The previous round yielded extremely weak interface affinity (max ipTM = {max_iptm:.2f} < 0.70). "
                            "Switching generator to RFdiffusion3 to support atom-level hotspot precision and "
                            "strong structural complementarity. Also recommending increasing the target binder length to expand contact area."
                        )
                    else:
                        next_tool = "bindcraft"
                        rationale = (
                            f"Weak interface confidence (max ipTM = {max_iptm:.2f}). Escalating to BindCraft "
                            "to leverage deep AlphaFold-multimer recycles and localized structural optimization."
                        )
                    length = int(
                        _as_float(prev_params.get("binder_length", 100)) or 100
                    )
                    if mean_sasa < 1100:
                        next_params["binder_length"] = length + 15
                    else:
                        next_params["binder_length"] = length + 5

                elif mean_clashes > 5 or mean_rmsd > 3.0:
                    status_summary = "high_clashes_increase_refinement"
                    next_tool = "bindcraft"
                    rationale = (
                        f"High physical clashes (mean clashes = {mean_clashes:.1f}) or conformation drift (mean RMSD = {mean_rmsd:.1f} > 3.0) "
                        "were detected in the candidates. Switching to or staying with BindCraft, and increasing refinement/recycle iterations "
                        "to perform full relaxation of steric clashes."
                    )
                    next_params["iterations"] = 75
                    next_params["refine_clashes"] = True
                else:
                    status_summary = "tweak_parameters"
                    next_tool = prev_tool
                    rationale = (
                        f"No dominant failure mode detected (max ipTM = {max_iptm:.2f}, mean pLDDT = {mean_plddt:.1f}). "
                        "Tweak parameters (e.g., increase sample size to explore more conformational spaces)."
                    )
                    next_params["num_samples"] = int(
                        prev_params.get("num_samples", 100) * 1.5
                    )

            next_params_str = "\n".join(
                f"- **{k}:** {v}" for k, v in next_params.items()
            )

            plan_path = None
            if project_dir:
                plan_path = project_dir / "next_round_plan.md"

                prev_tool_val = prev_tool or "Unknown"
                prev_params_val = json.dumps(prev_params)
                cand_count_val = candidate_count

                if candidate_count > 0:
                    retrospect_lines = (
                        f"- **Max / Mean ipTM:** {max_iptm:.2f} / {mean_iptm:.2f}\n"
                        f"- **Max / Mean pLDDT:** {max_plddt:.1f} / {mean_plddt:.1f}\n"
                        f"- **Mean Clashes:** {mean_clashes:.1f}\n"
                        f"- **Mean RMSD:** {mean_rmsd:.1f} Å\n"
                        f"- **Buried SASA:** {mean_sasa:.1f} Å²\n"
                        f"- **Mean Contacts:** {mean_contacts:.1f}\n"
                    )
                else:
                    retrospect_lines = "- **Performance Summary:** No candidates were generated (OOM, Timeout, or Execution Error).\n"

                report_content = (
                    "# AI-DLC Inception Artifact: Next Round Design Plan\n\n"
                    "## 1. Previous Round Retrospective\n"
                    f"- **Generator Tool:** {prev_tool_val}\n"
                    f"- **Parameters:** {prev_params_val}\n"
                    f"- **Candidate Count:** {cand_count_val}\n"
                    f"{retrospect_lines}\n"
                    "## 2. Adaptive Optimization Decisions\n"
                    f"- **Transition Status:** {status_summary.upper()}\n"
                    f"- **Recommended Next Tool:** {next_tool}\n"
                    "## 3. Recommended Parameters\n"
                    f"{next_params_str}\n\n"
                    "### Rationale & Heuristics\n"
                    f"{rationale}\n\n"
                    "## 4. Step-by-Step Next Action Checklist (AI-DLC Construction)\n"
                    f"- [ ] 1. Initialize the new run directory under `outputs/` using `{next_tool}`\n"
                    f"- [ ] 2. Execute the recommended tool `{next_tool}` with the optimized parameters\n"
                    "- [ ] 3. Run orthogonal validation (Chai-1 and Protenix) on the new candidates\n"
                    "- [ ] 4. Cluster candidates and compare with the previous round's representatives\n"
                )
                try:
                    plan_path.write_text(report_content, encoding="utf-8")
                except Exception as exc:
                    return _format_result(
                        {
                            "status": "error",
                            "message": f"Failed to write next_round_plan.md: {exc}",
                        }
                    ), False

            if manifest and project_dir:
                manifest_path = project_dir / "binder_project.json"
                manifest.setdefault("campaign_history", []).append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "tool_used": prev_tool,
                        "parameters_used": prev_params,
                        "candidate_count": candidate_count,
                        "status": status_summary,
                    }
                )
                manifest["next_round_optimization"] = {
                    "tool": next_tool,
                    "parameters": next_params,
                    "rationale": rationale,
                    "audit_plan": str(plan_path) if plan_path else None,
                }
                if next_tool not in manifest.get("tools", []):
                    manifest.setdefault("tools", []).append(next_tool)
                try:
                    manifest_path.write_text(
                        _format_result(manifest) + "\n", encoding="utf-8"
                    )
                except Exception as exc:
                    return _format_result(
                        {
                            "status": "error",
                            "message": f"Failed to update binder_project.json: {exc}",
                        }
                    ), False

            return (
                _format_result(
                    {
                        "status": "optimized",
                        "transition_status": status_summary,
                        "previous_candidate_count": candidate_count,
                        "next_round_tool": next_tool,
                        "next_round_parameters": next_params,
                        "optimization_reason": rationale,
                        "audit_plan_path": str(plan_path) if plan_path else None,
                    }
                ),
                True,
            )

        if operation == "export_skill":
            project_dir = _safe_path(arguments.get("project_dir"))
            manifest_path = project_dir / "binder_project.json"
            if not manifest_path.exists():
                return (
                    _format_result(
                        {
                            "status": "error",
                            "message": (
                                f"Missing binder_project.json in {project_dir}. "
                                "Run create_project first."
                            ),
                        }
                    ),
                    False,
                )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            skill_name = _slugify_skill_name(arguments.get("skill_name"))
            skill_dir = project_dir / "skills"
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_path = skill_dir / f"{skill_name}.md"
            skill_path.write_text(
                _render_skill_card(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    skill_name=skill_name,
                )
                + "\n",
                encoding="utf-8",
            )
            return (
                _format_result(
                    {
                        "status": "exported",
                        "skill_name": skill_name,
                        "skill_path": str(skill_path),
                        "source_manifest": str(manifest_path),
                    }
                ),
                True,
            )

        if operation == "setup_tools":
            import asyncio

            project_root = Path(__file__).resolve().parents[2]
            script_path = project_root / "scripts" / "setup-proteinmcp-local.sh"
            if not script_path.exists():
                return (
                    _format_result(
                        {
                            "status": "error",
                            "message": f"Setup script not found at {script_path}",
                        }
                    ),
                    False,
                )

            requested_tools = arguments.get("tools") or ["all"]
            tool_mapping = {
                "bindcraft": "bindcraft_mcp",
                "bindcraft_mcp": "bindcraft_mcp",
                "boltzgen": "boltzgen_mcp",
                "boltzgen_mcp": "boltzgen_mcp",
                "pxdesign": "pxdesign_mcp",
                "pxdesign_mcp": "pxdesign_mcp",
                "all": "all",
            }

            targets = []
            for t in requested_tools:
                mapped = tool_mapping.get(t.lower())
                if mapped:
                    targets.append(mapped)
                else:
                    targets.append(t)

            targets = list(dict.fromkeys(targets))

            results = []
            success = True
            for target in targets:
                proc = await asyncio.create_subprocess_exec(
                    "bash",
                    str(script_path),
                    target,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(project_root),
                )
                stdout, stderr = await proc.communicate()
                ret = proc.returncode

                results.append(
                    {
                        "tool": target,
                        "exit_code": ret,
                        "stdout": stdout.decode("utf-8", errors="replace"),
                        "stderr": stderr.decode("utf-8", errors="replace"),
                    }
                )
                if ret != 0:
                    success = False

            return (
                _format_result(
                    {
                        "status": "completed" if success else "failed",
                        "results": results,
                    }
                ),
                success,
            )

        if operation == "run_diagnostics":
            import io
            from agent.core.doctor import run_doctor

            buf = io.StringIO()
            exit_code = run_doctor(output=buf)
            report = buf.getvalue()
            return (
                _format_result(
                    {
                        "status": "healthy" if exit_code == 0 else "degraded",
                        "exit_code": exit_code,
                        "report": report,
                    }
                ),
                True,
            )

        return (
            _format_result(
                {
                    "status": "error",
                    "message": (
                        "Unknown or missing operation. Use plan_campaign, "
                        "create_project, inspect_outputs, rank_candidates, "
                        "export_skill, setup_tools, or run_diagnostics."
                    ),
                }
            ),
            False,
        )
    except Exception as exc:
        return _format_result({"status": "error", "message": str(exc)}), False
