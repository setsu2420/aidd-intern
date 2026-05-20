"""Local AIDD preparation workflow helpers.

The preparation stage is intentionally lightweight and deterministic: collect
paper metadata through the existing literature lookup tool, download a PDB file
from RCSB, crop PDB coordinates with fixed-column parsing, and rank candidate
interface hotspot residues from target/partner atom contacts.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, TextIO

import httpx

from agent.tools.literature_lookup_tool import literature_lookup_handler

RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"
DEFAULT_HOTSPOT_CUTOFF = 4.5
DEFAULT_LITERATURE_LIMIT = 5
MAX_LITERATURE_LIMIT = 20
MAX_HOTSPOTS = 50

HYDROPHOBIC_RESIDUES = {
    "ALA",
    "VAL",
    "LEU",
    "ILE",
    "MET",
    "PHE",
    "TRP",
    "TYR",
    "PRO",
}
AROMATIC_RESIDUES = {"PHE", "TRP", "TYR", "HIS"}
POLAR_ELEMENTS = {"N", "O", "S"}
WATER_RESIDUES = {"HOH", "WAT", "H2O"}


@dataclass(frozen=True)
class PdbAtom:
    line: str
    record: str
    chain_id: str
    residue_name: str
    residue_number: int
    insertion_code: str
    atom_name: str
    element: str
    x: float
    y: float
    z: float

    @property
    def residue_key(self) -> tuple[str, str, int, str]:
        return (
            self.chain_id,
            self.residue_name,
            self.residue_number,
            self.insertion_code,
        )


def _ok(payload: dict[str, Any]) -> tuple[str, bool]:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n", True


def _fail(message: str, **extra: Any) -> tuple[str, bool]:
    payload = {"status": "error", "message": message}
    payload.update(extra)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n", False


def _safe_path(raw: str | Path | None, *, default: Path | None = None) -> Path:
    if raw in (None, ""):
        if default is None:
            raise ValueError("path is required")
        return default.expanduser().resolve()
    return Path(raw).expanduser().resolve()


def _slugify(value: str) -> str:
    text = value.strip().lower()
    chars: list[str] = []
    for char in text:
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
    return "".join(chars).strip("-") or "aidd-target"


def _normalize_pdb_id(value: Any) -> str:
    pdb_id = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{4}", pdb_id):
        raise ValueError("pdb_id must be a 4-character RCSB PDB id")
    return pdb_id


def _parse_chain_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;\s]+", value.strip())
    elif isinstance(value, Iterable):
        parts = [str(item) for item in value]
    else:
        parts = [str(value)]
    chains = [part.strip() for part in parts if part.strip()]
    return chains


def _parse_residue_ranges(value: Any) -> dict[str, list[tuple[int, int]]]:
    """Parse ranges such as A:19-134,B:50-75 into chain-indexed intervals."""

    if value in (None, ""):
        return {}
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[,;]+", value) if part.strip()]
    elif isinstance(value, Iterable):
        parts = [str(item).strip() for item in value if str(item).strip()]
    else:
        parts = [str(value).strip()]

    ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for part in parts:
        if ":" in part:
            chain, raw_range = part.split(":", 1)
            chain = chain.strip()
        else:
            chain = "*"
            raw_range = part
        match = re.fullmatch(r"(-?\d+)(?:-(-?\d+))?", raw_range.strip())
        if not match:
            raise ValueError("residue_ranges must look like 'A:19-134' or '19-134'")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if end < start:
            start, end = end, start
        ranges[chain].append((start, end))
    return dict(ranges)


def _range_allows(
    atom: PdbAtom, ranges_by_chain: dict[str, list[tuple[int, int]]]
) -> bool:
    if not ranges_by_chain:
        return True
    ranges = ranges_by_chain.get(atom.chain_id) or ranges_by_chain.get("*") or []
    return any(start <= atom.residue_number <= end for start, end in ranges)


def _parse_pdb_atom(line: str) -> PdbAtom | None:
    record = line[:6].strip()
    if record not in {"ATOM", "HETATM"}:
        return None
    try:
        atom_name = line[12:16].strip()
        residue_name = line[17:20].strip()
        chain_id = line[21].strip() or "_"
        residue_number = int(line[22:26])
        insertion_code = line[26].strip()
        x = float(line[30:38])
        y = float(line[38:46])
        z = float(line[46:54])
    except (IndexError, ValueError):
        return None

    element = line[76:78].strip().upper()
    if not element:
        element = re.sub(r"[^A-Za-z]", "", atom_name[:2]).upper()[:1]
    return PdbAtom(
        line=line.rstrip("\n"),
        record=record,
        chain_id=chain_id,
        residue_name=residue_name,
        residue_number=residue_number,
        insertion_code=insertion_code,
        atom_name=atom_name,
        element=element,
        x=x,
        y=y,
        z=z,
    )


def _load_atoms(path: Path, *, include_hetero: bool = False) -> list[PdbAtom]:
    atoms: list[PdbAtom] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        atom = _parse_pdb_atom(line)
        if atom is None:
            continue
        if atom.element == "H":
            continue
        if atom.record == "HETATM" and not include_hetero:
            continue
        if atom.residue_name in WATER_RESIDUES:
            continue
        atoms.append(atom)
    return atoms


def _residue_label(residue: tuple[str, str, int, str]) -> str:
    chain, name, number, insertion = residue
    suffix = insertion if insertion else ""
    return f"{chain}:{name}{number}{suffix}"


def _distance(first: PdbAtom, second: PdbAtom) -> float:
    return math.sqrt(
        (first.x - second.x) ** 2
        + (first.y - second.y) ** 2
        + (first.z - second.z) ** 2
    )


def _project_dir_from_args(args: dict[str, Any]) -> Path:
    project_dir = args.get("project_dir")
    if project_dir:
        return _safe_path(project_dir)
    target_name = str(args.get("target_name") or "aidd-target")
    return Path.cwd() / "aidd-prep" / _slugify(target_name)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", "utf-8")


def _default_research_query(target_name: str) -> str:
    return (
        f"{target_name} binder design structure hotspot epitope PDB "
        "protein-protein interaction"
    )


def _preparation_manifest(
    *,
    target_name: str,
    project_dir: Path,
    pdb_id: str | None = None,
    target_chains: list[str] | None = None,
    partner_chains: list[str] | None = None,
    residue_ranges: Any = None,
    research_query: str | None = None,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "project_dir": str(project_dir),
        "target_name": target_name,
        "pdb_id": pdb_id,
        "target_chains": target_chains or [],
        "partner_chains": partner_chains or [],
        "residue_ranges": residue_ranges or "",
        "research_query": research_query or _default_research_query(target_name),
        "required_stages": [
            "literature_research",
            "pdb_download",
            "structure_cropping",
            "hotspot_residue_determination",
        ],
        "artifacts": {},
    }


def _render_research_plan(manifest: dict[str, Any]) -> str:
    query = manifest["research_query"]
    target = manifest["target_name"]
    return "\n".join(
        [
            f"# AIDD Preparation Research Plan: {target}",
            "",
            "## Required Questions",
            "- What is the target biology and disease relevance?",
            "- Which PDB structures, assemblies, chains, cofactors, glycans, or PTMs matter?",
            "- Which known binders, ligands, antibodies, or natural partners define the epitope?",
            "- Which residues are reported or implied as interface hotspots?",
            "- Which no-go regions or assay constraints should carry into binder design?",
            "",
            "## Literature Query",
            f"`{query}`",
            "",
            "## Tool Order",
            '1. `literature_lookup(operation="search", sources="all")`',
            "2. `web_search` for current official pages and recent releases",
            "3. `aidd_bio` for RCSB, UniProt, AlphaFold DB, and Foldseek checks",
            "4. `aidd_prepare` for PDB download, cropping, and hotspot files",
            "",
        ]
    )


async def _create_project(args: dict[str, Any]) -> tuple[str, bool]:
    target_name = str(args.get("target_name") or "").strip()
    if not target_name:
        return _fail("target_name is required for create_project")

    project_dir = _project_dir_from_args(args)
    for child in [
        "literature",
        "structures/raw",
        "structures/cropped",
        "analysis",
    ]:
        (project_dir / child).mkdir(parents=True, exist_ok=True)

    pdb_id = None
    if args.get("pdb_id"):
        pdb_id = _normalize_pdb_id(args.get("pdb_id"))
    target_chains = _parse_chain_list(args.get("target_chains"))
    partner_chains = _parse_chain_list(args.get("partner_chains"))
    research_query = str(args.get("research_query") or "").strip() or None
    manifest = _preparation_manifest(
        target_name=target_name,
        project_dir=project_dir,
        pdb_id=pdb_id,
        target_chains=target_chains,
        partner_chains=partner_chains,
        residue_ranges=args.get("residue_ranges"),
        research_query=research_query,
    )
    manifest_path = project_dir / "aidd_preparation_manifest.json"
    _write_json(manifest_path, manifest)
    research_plan_path = project_dir / "literature" / "research_plan.md"
    research_plan_path.write_text(_render_research_plan(manifest), encoding="utf-8")
    return _ok(
        {
            "status": "created",
            "project_dir": str(project_dir),
            "manifest": str(manifest_path),
            "research_plan": str(research_plan_path),
        }
    )


async def _literature_research(args: dict[str, Any]) -> tuple[str, bool]:
    target_name = str(args.get("target_name") or "").strip()
    query = str(args.get("research_query") or "").strip()
    if not query:
        if not target_name:
            return _fail("target_name or research_query is required")
        query = _default_research_query(target_name)

    limit = int(args.get("limit") or DEFAULT_LITERATURE_LIMIT)
    limit = max(1, min(limit, MAX_LITERATURE_LIMIT))
    project_dir = _project_dir_from_args(args)
    literature_dir = project_dir / "literature"
    literature_dir.mkdir(parents=True, exist_ok=True)

    text, ok = await literature_lookup_handler(
        {
            "operation": "search",
            "query": query,
            "sources": args.get("sources") or "all",
            "limit": limit,
        }
    )
    output_path = literature_dir / "literature_sources.md"
    output_path.write_text(text, encoding="utf-8")
    return _ok(
        {
            "status": "researched" if ok else "research_failed",
            "query": query,
            "literature_sources": str(output_path),
            "ok": ok,
        }
    )


async def _download_pdb(args: dict[str, Any]) -> tuple[str, bool]:
    pdb_id = _normalize_pdb_id(args.get("pdb_id") or args.get("id"))
    file_format = str(args.get("file_format") or "pdb").strip().lower()
    if file_format not in {"pdb", "cif", "bcif"}:
        return _fail("file_format must be one of: pdb, cif, bcif")

    project_dir = _project_dir_from_args(args)
    default_path = project_dir / "structures" / "raw" / f"{pdb_id}.{file_format}"
    output_path = _safe_path(args.get("output_path"), default=default_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    url = f"{RCSB_DOWNLOAD_URL}/{pdb_id}.{file_format}"
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
    text = response.text
    if file_format == "pdb" and "ATOM" not in text and "HETATM" not in text:
        return _fail("downloaded file does not look like a coordinate file", url=url)

    output_path.write_text(text, encoding="utf-8")
    return _ok(
        {
            "status": "downloaded",
            "pdb_id": pdb_id,
            "source": url,
            "path": str(output_path),
            "bytes": output_path.stat().st_size,
        }
    )


async def _crop_structure(args: dict[str, Any]) -> tuple[str, bool]:
    input_path = _safe_path(args.get("input_path") or args.get("pdb_path"))
    if not input_path.exists():
        return _fail(f"input_path does not exist: {input_path}")
    chains = _parse_chain_list(args.get("chains") or args.get("target_chains"))
    if not chains:
        return _fail("chains or target_chains is required for crop_structure")
    ranges_by_chain = _parse_residue_ranges(args.get("residue_ranges"))
    include_hetero = bool(args.get("include_hetero") or False)
    include_waters = bool(args.get("include_waters") or False)

    default_name = f"{input_path.stem}_{''.join(chains)}_crop.pdb"
    default_path = input_path.parent.parent / "cropped" / default_name
    output_path = _safe_path(args.get("output_path"), default=default_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    selected_lines: list[str] = []
    selected_residues: set[tuple[str, str, int, str]] = set()
    total_atoms = 0
    for line in input_path.read_text(encoding="utf-8", errors="replace").splitlines():
        atom = _parse_pdb_atom(line)
        if atom is None:
            continue
        total_atoms += 1
        if atom.chain_id not in chains:
            continue
        if atom.record == "HETATM" and not include_hetero:
            continue
        if atom.residue_name in WATER_RESIDUES and not include_waters:
            continue
        if not _range_allows(atom, ranges_by_chain):
            continue
        selected_lines.append(atom.line)
        selected_residues.add(atom.residue_key)

    if not selected_lines:
        return _fail(
            "crop_structure selected zero atoms",
            input_path=str(input_path),
            chains=chains,
            residue_ranges=args.get("residue_ranges") or "",
        )

    header = [
        "REMARK AIDD-Intern cropped structure",
        f"REMARK Source: {input_path}",
        f"REMARK Chains: {','.join(chains)}",
    ]
    if args.get("residue_ranges"):
        header.append(f"REMARK Residue ranges: {args.get('residue_ranges')}")
    output_path.write_text(
        "\n".join([*header, *selected_lines, "TER", "END", ""]),
        encoding="utf-8",
    )
    return _ok(
        {
            "status": "cropped",
            "input_path": str(input_path),
            "output_path": str(output_path),
            "chains": chains,
            "residue_ranges": args.get("residue_ranges") or "",
            "source_atom_count": total_atoms,
            "selected_atom_count": len(selected_lines),
            "selected_residue_count": len(selected_residues),
        }
    )


def _rank_hotspots(
    *,
    atoms: list[PdbAtom],
    target_chains: list[str],
    partner_chains: list[str],
    cutoff: float,
) -> list[dict[str, Any]]:
    target_atoms = [atom for atom in atoms if atom.chain_id in target_chains]
    partner_atoms = [atom for atom in atoms if atom.chain_id in partner_chains]
    grouped: dict[tuple[str, str, int, str], dict[str, Any]] = {}

    for target_atom in target_atoms:
        for partner_atom in partner_atoms:
            distance = _distance(target_atom, partner_atom)
            if distance > cutoff:
                continue
            key = target_atom.residue_key
            row = grouped.setdefault(
                key,
                {
                    "residue": _residue_label(key),
                    "chain": target_atom.chain_id,
                    "residue_name": target_atom.residue_name,
                    "residue_number": target_atom.residue_number,
                    "insertion_code": target_atom.insertion_code,
                    "contact_count": 0,
                    "partner_residues": set(),
                    "min_distance": distance,
                    "hydrophobic_contacts": 0,
                    "aromatic_contacts": 0,
                    "polar_contacts": 0,
                    "atom_contacts": [],
                },
            )
            row["contact_count"] += 1
            row["partner_residues"].add(_residue_label(partner_atom.residue_key))
            row["min_distance"] = min(float(row["min_distance"]), distance)
            if (
                target_atom.residue_name in HYDROPHOBIC_RESIDUES
                or partner_atom.residue_name in HYDROPHOBIC_RESIDUES
            ):
                row["hydrophobic_contacts"] += 1
            if (
                target_atom.residue_name in AROMATIC_RESIDUES
                or partner_atom.residue_name in AROMATIC_RESIDUES
            ):
                row["aromatic_contacts"] += 1
            if target_atom.element in POLAR_ELEMENTS and partner_atom.element in {
                "N",
                "O",
            }:
                row["polar_contacts"] += 1
            if len(row["atom_contacts"]) < 8:
                row["atom_contacts"].append(
                    {
                        "target_atom": target_atom.atom_name,
                        "partner": _residue_label(partner_atom.residue_key),
                        "partner_atom": partner_atom.atom_name,
                        "distance": round(distance, 3),
                    }
                )

    ranked = []
    for row in grouped.values():
        partner_residues = sorted(row["partner_residues"])
        score = (
            float(row["contact_count"])
            + 0.75 * len(partner_residues)
            + 0.5 * float(row["hydrophobic_contacts"])
            + 0.75 * float(row["aromatic_contacts"])
            + 0.25 * float(row["polar_contacts"])
            - float(row["min_distance"]) / 10.0
        )
        row["partner_residues"] = partner_residues
        row["partner_residue_count"] = len(partner_residues)
        row["hotspot_score"] = round(score, 4)
        row["min_distance"] = round(float(row["min_distance"]), 3)
        ranked.append(row)

    ranked.sort(
        key=lambda item: (
            item["hotspot_score"],
            item["contact_count"],
            -item["min_distance"],
        ),
        reverse=True,
    )
    return ranked


async def _identify_hotspots(args: dict[str, Any]) -> tuple[str, bool]:
    input_path = _safe_path(args.get("input_path") or args.get("pdb_path"))
    if not input_path.exists():
        return _fail(f"input_path does not exist: {input_path}")
    target_chains = _parse_chain_list(args.get("target_chains"))
    partner_chains = _parse_chain_list(args.get("partner_chains"))
    if not target_chains or not partner_chains:
        return _fail("target_chains and partner_chains are required")
    cutoff = float(args.get("hotspot_cutoff") or args.get("cutoff") or 4.5)
    if cutoff <= 0:
        return _fail("hotspot cutoff must be positive")
    top_k = int(args.get("top_k") or MAX_HOTSPOTS)
    top_k = max(1, min(top_k, MAX_HOTSPOTS))
    include_hetero = bool(args.get("include_hetero") or False)

    atoms = _load_atoms(input_path, include_hetero=include_hetero)
    hotspots = _rank_hotspots(
        atoms=atoms,
        target_chains=target_chains,
        partner_chains=partner_chains,
        cutoff=cutoff,
    )
    payload = {
        "status": "hotspots_identified",
        "method": (
            "candidate interface hotspots ranked from non-hydrogen target/partner "
            "atom contacts; confirm with literature or mutagenesis before wet-lab use"
        ),
        "input_path": str(input_path),
        "target_chains": target_chains,
        "partner_chains": partner_chains,
        "cutoff_angstrom": cutoff,
        "atom_count": len(atoms),
        "hotspot_count": len(hotspots),
        "hotspots": hotspots[:top_k],
    }

    default_path = input_path.parent.parent / "analysis" / "hotspots.json"
    output_path = _safe_path(args.get("output_path"), default=default_path)
    _write_json(output_path, payload)
    payload["output_path"] = str(output_path)
    return _ok(payload)


def _read_json_text(text: str) -> dict[str, Any]:
    return json.loads(text)


async def _run_preparation(args: dict[str, Any]) -> tuple[str, bool]:
    required = ["target_name", "pdb_id", "target_chains", "partner_chains"]
    missing = [key for key in required if not args.get(key)]
    if missing:
        return _fail(
            "run_preparation requires target_name, pdb_id, target_chains, "
            "and partner_chains",
            missing=missing,
        )

    project_text, ok = await _create_project(args)
    if not ok:
        return project_text, ok
    project = _read_json_text(project_text)
    project_dir = Path(project["project_dir"])

    literature_text, literature_ok = await _literature_research(args)
    literature = _read_json_text(literature_text)

    download_text, ok = await _download_pdb(args)
    if not ok:
        return download_text, ok
    downloaded = _read_json_text(download_text)
    raw_path = downloaded["path"]

    hotspot_args = {
        **args,
        "input_path": raw_path,
        "output_path": str(project_dir / "analysis" / "hotspots.json"),
    }
    hotspots_text, ok = await _identify_hotspots(hotspot_args)
    if not ok:
        return hotspots_text, ok
    hotspots = _read_json_text(hotspots_text)

    crop_args = {
        **args,
        "input_path": raw_path,
        "chains": args.get("chains") or args.get("target_chains"),
        "output_path": str(
            project_dir
            / "structures"
            / "cropped"
            / f"{downloaded['pdb_id']}_{''.join(_parse_chain_list(args.get('target_chains')))}_crop.pdb"
        ),
    }
    crop_text, ok = await _crop_structure(crop_args)
    if not ok:
        return crop_text, ok
    cropped = _read_json_text(crop_text)

    manifest_path = project_dir / "aidd_preparation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"] = {
        "literature_sources": literature.get("literature_sources"),
        "raw_pdb": raw_path,
        "cropped_structure": cropped["output_path"],
        "hotspots": hotspots["output_path"],
    }
    manifest["stage_status"] = {
        "literature_research": "complete" if literature_ok else "failed",
        "pdb_download": "complete",
        "structure_cropping": "complete",
        "hotspot_residue_determination": "complete",
    }
    _write_json(manifest_path, manifest)

    summary_path = project_dir / "aidd_preparation_summary.md"
    top_hotspots = [
        f"- {item['residue']}: score={item['hotspot_score']}, "
        f"contacts={item['contact_count']}, partners={', '.join(item['partner_residues'][:6])}"
        for item in hotspots.get("hotspots", [])[:10]
    ]
    summary_path.write_text(
        "\n".join(
            [
                f"# AIDD Preparation Summary: {args['target_name']}",
                "",
                "## Artifacts",
                f"- Literature sources: {literature.get('literature_sources')}",
                f"- Raw PDB: {raw_path}",
                f"- Cropped structure: {cropped['output_path']}",
                f"- Hotspot residues: {hotspots['output_path']}",
                "",
                "## Top Candidate Hotspot Residues",
                *(top_hotspots or ["- none found"]),
                "",
                "## Method Note",
                (
                    "Hotspots are contact-derived candidates from the supplied "
                    "target/partner chains. Treat them as design-preparation "
                    "inputs, not as experimental binding-energy proof."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    return _ok(
        {
            "status": "prepared",
            "project_dir": str(project_dir),
            "manifest": str(manifest_path),
            "summary": str(summary_path),
            "literature_ok": literature_ok,
            "artifacts": manifest["artifacts"],
            "top_hotspots": hotspots.get("hotspots", [])[:10],
        }
    )


_OPERATIONS = {
    "create_project": _create_project,
    "literature_research": _literature_research,
    "download_pdb": _download_pdb,
    "crop_structure": _crop_structure,
    "identify_hotspots": _identify_hotspots,
    "run_preparation": _run_preparation,
}


AIDD_PREPARE_TOOL_SPEC = {
    "name": "aidd_prepare",
    "description": (
        "Run the AIDD preparation stage: literature source collection, RCSB PDB "
        "download, PDB structure cropping, and target/partner contact-derived "
        "hotspot residue determination."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": list(_OPERATIONS),
                "description": "Preparation operation to execute.",
            },
            "target_name": {"type": "string"},
            "project_dir": {"type": "string"},
            "research_query": {"type": "string"},
            "sources": {"type": "string", "default": "all"},
            "limit": {"type": "integer", "default": DEFAULT_LITERATURE_LIMIT},
            "pdb_id": {"type": "string", "description": "RCSB PDB id, e.g. 4ZQK."},
            "id": {"type": "string", "description": "Alias for pdb_id."},
            "file_format": {
                "type": "string",
                "enum": ["pdb", "cif", "bcif"],
                "default": "pdb",
            },
            "input_path": {"type": "string"},
            "pdb_path": {"type": "string", "description": "Alias for input_path."},
            "output_path": {"type": "string"},
            "chains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Chains to keep during cropping.",
            },
            "target_chains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Target chain ids for cropping and hotspot ranking.",
            },
            "partner_chains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Binding partner chain ids for hotspot ranking.",
            },
            "residue_ranges": {
                "type": "string",
                "description": "Ranges to keep, e.g. 'A:19-134,B:50-80'.",
            },
            "include_hetero": {"type": "boolean", "default": False},
            "include_waters": {"type": "boolean", "default": False},
            "hotspot_cutoff": {
                "type": "number",
                "default": DEFAULT_HOTSPOT_CUTOFF,
                "description": "Target/partner atom contact cutoff in Angstrom.",
            },
            "cutoff": {
                "type": "number",
                "description": "Alias for hotspot_cutoff.",
            },
            "top_k": {"type": "integer", "default": 10},
        },
        "required": ["operation"],
        "additionalProperties": False,
    },
}


async def aidd_prepare_handler(arguments: dict[str, Any]) -> tuple[str, bool]:
    operation = arguments.get("operation")
    if not operation:
        return _fail("'operation' parameter is required")
    handler = _OPERATIONS.get(str(operation))
    if handler is None:
        return _fail(f"Unknown operation: {operation}", valid=list(_OPERATIONS))
    try:
        return await handler(arguments)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        return _fail(
            "HTTP error during AIDD preparation",
            status_code=exc.response.status_code if exc.response else None,
            body=body,
        )
    except httpx.RequestError as exc:
        return _fail(f"Request error during AIDD preparation: {exc}")
    except Exception as exc:
        return _fail(f"Error in {operation}: {exc}")


async def run_aidd_preparation_cli(
    *,
    target_name: str | None,
    pdb_id: str | None,
    target_chains: str | None,
    partner_chains: str | None,
    project_dir: str | None = None,
    residue_ranges: str | None = None,
    research_query: str | None = None,
    literature_limit: int = DEFAULT_LITERATURE_LIMIT,
    hotspot_cutoff: float = DEFAULT_HOTSPOT_CUTOFF,
    output: TextIO | None = None,
) -> int:
    out = output or sys.stdout
    missing = [
        name
        for name, value in {
            "--target-name": target_name,
            "--pdb-id": pdb_id,
            "--target-chains": target_chains,
            "--partner-chains": partner_chains,
        }.items()
        if not value
    ]
    if missing:
        message = "Missing required AIDD preparation options: " + ", ".join(missing)
        print(message, file=out)
        return 2

    args = {
        "operation": "run_preparation",
        "target_name": target_name,
        "pdb_id": pdb_id,
        "target_chains": _parse_chain_list(target_chains),
        "partner_chains": _parse_chain_list(partner_chains),
        "project_dir": project_dir,
        "residue_ranges": residue_ranges,
        "research_query": research_query,
        "limit": literature_limit,
        "hotspot_cutoff": hotspot_cutoff,
    }
    print("STEP 1: Creating AIDD preparation project", file=out)
    print("STEP 2: Searching literature metadata", file=out)
    print("STEP 3: Downloading PDB coordinates from RCSB", file=out)
    print("STEP 4: Cropping target structure", file=out)
    print("STEP 5: Determining candidate hotspot residues", file=out)

    text, ok = await _run_preparation(args)
    print(text.rstrip(), file=out)
    return 0 if ok else 1
