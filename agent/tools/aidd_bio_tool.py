"""AIDD biomedical structure and protein database tool.

Integrates public APIs from RCSB PDB, AlphaFold DB, UniProt, and the Foldseek
search server. The tool returns bounded, citation-friendly text so the agent can
use these resources without dumping full structure files into context.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

import httpx

from agent.tools.types import ToolResult

RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_DATA_URL = "https://data.rcsb.org/rest/v1/core"
RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"
ALPHAFOLD_API_URL = "https://alphafold.ebi.ac.uk/api"
UNIPROT_API_URL = "https://rest.uniprot.org/uniprotkb"
FOLDSEEK_URL = "https://search.foldseek.com"

DEFAULT_LIMIT = 5
MAX_LIMIT = 25
DEFAULT_MAX_CHARS = 12000
MAX_CHARS = 50000


def _limit(value: Any, default: int = DEFAULT_LIMIT) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, MAX_LIMIT))


def _max_chars(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_CHARS
    return max(1000, min(parsed, MAX_CHARS))


def _as_text_block(title: str, source: str, content: str, max_chars: int) -> str:
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    suffix = "\n\n...(truncated)..." if truncated else ""
    return f"# {title}\nSource: {source}\n\n```\n{content}{suffix}\n```"


def _json_preview(data: Any, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...(truncated)..."


def _pick(data: dict[str, Any], path: Iterable[str], default: Any = None) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


async def _get_json(url: str, **kwargs: Any) -> Any:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _post_json(url: str, payload: dict[str, Any], **kwargs: Any) -> Any:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.post(url, json=payload, **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _get_text(url: str, **kwargs: Any) -> str:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text


async def _foldseek_post_form(url: str, data: list[tuple[str, str]], query: str) -> Any:
    files = {"q": ("query.pdb", query.encode("utf-8"), "chemical/x-pdb")}
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.post(url, data=data, files=files)
        resp.raise_for_status()
        return resp.json()


def _ok(formatted: str, total: int = 1, shared: int | None = None) -> ToolResult:
    return {
        "formatted": formatted,
        "totalResults": total,
        "resultsShared": total if shared is None else shared,
    }


def _error(message: str) -> ToolResult:
    return {
        "formatted": message,
        "totalResults": 0,
        "resultsShared": 0,
        "isError": True,
    }


async def _rcsb_search(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return _error("'query' is required for rcsb_search.")
    limit = _limit(args.get("limit"))
    payload = {
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": query},
        },
        "return_type": args.get("return_type", "entry"),
        "request_options": {
            "paginate": {"start": 0, "rows": limit},
            "scoring_strategy": "combined",
        },
    }
    data = await _post_json(RCSB_SEARCH_URL, payload)
    results = data.get("result_set") or []
    lines = [
        f"# RCSB Search: {query}",
        f"Source: {RCSB_SEARCH_URL}",
        f"Total: {data.get('total_count', len(results))}",
        "",
    ]
    for idx, item in enumerate(results, 1):
        identifier = item.get("identifier", "")
        score = item.get("score")
        lines.append(
            f"{idx}. {identifier}"
            + (f" (score {score:.3f})" if isinstance(score, (int, float)) else "")
            + f"\n   https://www.rcsb.org/structure/{identifier}"
        )
    return _ok(
        "\n".join(lines),
        total=data.get("total_count", len(results)),
        shared=len(results),
    )


async def _rcsb_entry(args: dict[str, Any]) -> ToolResult:
    entry_id = str(args.get("id") or args.get("entry_id") or "").strip().upper()
    if not entry_id:
        return _error("'id' is required for rcsb_entry.")
    data = await _get_json(f"{RCSB_DATA_URL}/entry/{entry_id}")
    title = _pick(data, ("struct", "title"), "")
    method = _pick(data, ("rcsb_entry_info", "experimental_method"), "")
    resolution = _pick(data, ("rcsb_entry_info", "resolution_combined"), [])
    citation = _pick(data, ("rcsb_primary_citation", "title"), "")
    lines = [
        f"# RCSB Entry {entry_id}",
        f"Source: {RCSB_DATA_URL}/entry/{entry_id}",
        f"Structure: https://www.rcsb.org/structure/{entry_id}",
        "",
        f"Title: {title}",
        f"Method: {method}",
        f"Resolution: {resolution}",
        f"Primary citation: {citation}",
        "",
        "## JSON Preview",
        "```json",
        _json_preview(data, _max_chars(args.get("max_chars"))),
        "```",
    ]
    return _ok("\n".join(lines))


async def _rcsb_download(args: dict[str, Any]) -> ToolResult:
    entry_id = str(args.get("id") or args.get("entry_id") or "").strip().upper()
    fmt = str(args.get("file_format") or "cif").strip().lower()
    if not entry_id:
        return _error("'id' is required for rcsb_download.")
    if fmt not in {"pdb", "cif", "bcif"}:
        return _error("file_format must be one of: pdb, cif, bcif.")
    url = f"{RCSB_DOWNLOAD_URL}/{entry_id}.{fmt}"
    text = await _get_text(url)
    return _ok(
        _as_text_block(
            f"RCSB {entry_id}.{fmt}", url, text, _max_chars(args.get("max_chars"))
        )
    )


async def _alphafold_prediction(args: dict[str, Any]) -> ToolResult:
    accession = str(
        args.get("accession") or args.get("uniprot_accession") or ""
    ).strip()
    if not accession:
        return _error("'accession' is required for alphafold_prediction.")
    url = f"{ALPHAFOLD_API_URL}/prediction/{accession}"
    data = await _get_json(url)
    rows = data if isinstance(data, list) else [data]
    lines = [f"# AlphaFold DB Prediction: {accession}", f"Source: {url}", ""]
    for idx, row in enumerate(rows[: _limit(args.get("limit"))], 1):
        lines.extend(
            [
                f"## {idx}. {row.get('entryId') or row.get('modelEntityId')}",
                f"UniProt: {row.get('uniprotAccession')} ({row.get('uniprotId')})",
                f"Description: {row.get('uniprotDescription')}",
                f"Organism: {row.get('organismScientificName')}",
                f"pLDDT/global metric: {row.get('globalMetricValue')}",
                f"PDB: {row.get('pdbUrl')}",
                f"mmCIF: {row.get('cifUrl')}",
                f"PAE JSON: {row.get('paeDocUrl')}",
                "",
            ]
        )
    return _ok(
        "\n".join(lines),
        total=len(rows),
        shared=min(len(rows), _limit(args.get("limit"))),
    )


async def _alphafold_download(args: dict[str, Any]) -> ToolResult:
    accession = str(
        args.get("accession") or args.get("uniprot_accession") or ""
    ).strip()
    file_type = str(args.get("file_type") or "pdb").strip().lower()
    if not accession:
        return _error("'accession' is required for alphafold_download.")
    if file_type not in {"pdb", "cif", "bcif", "pae", "plddt", "msa"}:
        return _error("file_type must be one of: pdb, cif, bcif, pae, plddt, msa.")
    data = await _get_json(f"{ALPHAFOLD_API_URL}/prediction/{accession}")
    rows = data if isinstance(data, list) else [data]
    if not rows:
        return _error(f"No AlphaFold DB predictions found for {accession}.")
    url_key = {
        "pdb": "pdbUrl",
        "cif": "cifUrl",
        "bcif": "bcifUrl",
        "pae": "paeDocUrl",
        "plddt": "plddtDocUrl",
        "msa": "msaUrl",
    }[file_type]
    url = rows[0].get(url_key)
    if not url:
        return _error(f"AlphaFold prediction for {accession} has no {file_type} URL.")
    text = await _get_text(url)
    return _ok(
        _as_text_block(
            f"AlphaFold {accession} {file_type}",
            url,
            text,
            _max_chars(args.get("max_chars")),
        )
    )


async def _uniprot_search(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return _error("'query' is required for uniprot_search.")
    limit = _limit(args.get("limit"))
    fields = str(
        args.get("fields")
        or "accession,id,protein_name,gene_names,organism_name,length,reviewed"
    )
    data = await _get_json(
        f"{UNIPROT_API_URL}/search",
        params={"query": query, "fields": fields, "format": "json", "size": limit},
    )
    results = data.get("results") or []
    lines = [
        f"# UniProt Search: {query}",
        "Source: https://rest.uniprot.org/uniprotkb/search",
        "",
    ]
    for idx, row in enumerate(results, 1):
        protein = _pick(
            row, ("proteinDescription", "recommendedName", "fullName", "value"), ""
        )
        gene = _pick(row, ("genes",), [])
        gene_name = ""
        if gene and isinstance(gene, list):
            gene_name = _pick(gene[0], ("geneName", "value"), "")
        lines.extend(
            [
                f"{idx}. {row.get('primaryAccession')} ({row.get('uniProtkbId')})",
                f"   Protein: {protein}",
                f"   Gene: {gene_name}",
                f"   Organism: {_pick(row, ('organism', 'scientificName'), '')}",
                f"   Length: {_pick(row, ('sequence', 'length'), '')}",
                f"   https://www.uniprot.org/uniprotkb/{row.get('primaryAccession')}",
            ]
        )
    total = data.get("results", [])
    return _ok("\n".join(lines), total=len(total), shared=len(results))


async def _uniprot_entry(args: dict[str, Any]) -> ToolResult:
    accession = str(args.get("accession") or "").strip()
    if not accession:
        return _error("'accession' is required for uniprot_entry.")
    url = f"{UNIPROT_API_URL}/{accession}.json"
    data = await _get_json(url)
    return _ok(
        "\n".join(
            [
                f"# UniProt Entry {accession}",
                f"Source: {url}",
                f"Record: https://www.uniprot.org/uniprotkb/{accession}",
                "",
                "```json",
                _json_preview(data, _max_chars(args.get("max_chars"))),
                "```",
            ]
        )
    )


async def _uniprot_download(args: dict[str, Any]) -> ToolResult:
    accession = str(args.get("accession") or "").strip()
    fmt = str(args.get("file_format") or "fasta").strip().lower()
    if not accession:
        return _error("'accession' is required for uniprot_download.")
    if fmt not in {"fasta", "json", "txt", "xml"}:
        return _error("file_format must be one of: fasta, json, txt, xml.")
    url = f"{UNIPROT_API_URL}/{accession}.{fmt}"
    text = await _get_text(url)
    return _ok(
        _as_text_block(
            f"UniProt {accession}.{fmt}", url, text, _max_chars(args.get("max_chars"))
        )
    )


async def _foldseek_databases(args: dict[str, Any]) -> ToolResult:
    data = await _get_json(f"{FOLDSEEK_URL}/api/databases/all")
    databases = data.get("databases") or []
    lines = ["# Foldseek Databases", f"Source: {FOLDSEEK_URL}/api/databases/all", ""]
    for db in databases[: _limit(args.get("limit"), 20)]:
        flags = []
        for key in ("default", "taxonomy", "complex", "motif"):
            if db.get(key):
                flags.append(key)
        lines.append(
            f"- {db.get('path')} — {db.get('name')} {db.get('version')} "
            f"[{', '.join(flags)}] status={db.get('status')}"
        )
    return _ok(
        "\n".join(lines),
        total=len(databases),
        shared=min(len(databases), _limit(args.get("limit"), 20)),
    )


async def _foldseek_submit(args: dict[str, Any]) -> ToolResult:
    query_structure = str(args.get("query_structure") or "").strip()
    if not query_structure:
        return _error("'query_structure' is required for foldseek_submit.")
    databases = args.get("databases") or ["afdb50", "pdb100"]
    if isinstance(databases, str):
        databases = [databases]
    data: list[tuple[str, str]] = []
    mode = str(args.get("mode") or "3diaa")
    if mode:
        data.append(("mode", mode))
    email = str(args.get("email") or "").strip()
    if email:
        data.append(("email", email))
    for db in databases:
        data.append(("database[]", str(db)))
    result = await _foldseek_post_form(
        f"{FOLDSEEK_URL}/api/ticket", data, query_structure
    )
    ticket = result.get("id")
    lines = [
        "# Foldseek Submission",
        f"Source: {FOLDSEEK_URL}/api/ticket",
        f"Status: {result.get('status')}",
        f"Ticket: {ticket}",
    ]
    if ticket:
        lines.extend(
            [
                f"Queue: {FOLDSEEK_URL}/queue/{ticket}",
                f"Poll with: aidd_bio(operation='foldseek_status', ticket='{ticket}')",
            ]
        )
    return _ok("\n".join(lines))


async def _foldseek_status(args: dict[str, Any]) -> ToolResult:
    ticket = str(args.get("ticket") or "").strip()
    if not ticket:
        return _error("'ticket' is required for foldseek_status.")
    data = await _get_json(f"{FOLDSEEK_URL}/api/ticket/{ticket}")
    lines = [
        f"# Foldseek Ticket {ticket}",
        f"Source: {FOLDSEEK_URL}/api/ticket/{ticket}",
        f"Status: {data.get('status')}",
        f"Result page: {FOLDSEEK_URL}/result/{ticket}/0",
        "",
        "```json",
        _json_preview(data, _max_chars(args.get("max_chars"))),
        "```",
    ]
    return _ok("\n".join(lines))


async def _foldseek_result(args: dict[str, Any]) -> ToolResult:
    ticket = str(args.get("ticket") or "").strip()
    entry = int(args.get("entry") or 0)
    if not ticket:
        return _error("'ticket' is required for foldseek_result.")
    url = f"{FOLDSEEK_URL}/api/result/{ticket}/{entry}"
    data = await _get_json(url)
    return _ok(
        "\n".join(
            [
                f"# Foldseek Result {ticket}/{entry}",
                f"Source: {url}",
                f"Result page: {FOLDSEEK_URL}/result/{ticket}/{entry}",
                "",
                "```json",
                _json_preview(data, _max_chars(args.get("max_chars"))),
                "```",
            ]
        )
    )


async def _foldseek_download(args: dict[str, Any]) -> ToolResult:
    ticket = str(args.get("ticket") or "").strip()
    if not ticket:
        return _error("'ticket' is required for foldseek_download.")
    url = f"{FOLDSEEK_URL}/api/result/download/{ticket}"
    text = await _get_text(url)
    return _ok(
        _as_text_block(
            f"Foldseek download {ticket}", url, text, _max_chars(args.get("max_chars"))
        )
    )


_OPERATIONS = {
    "rcsb_search": _rcsb_search,
    "rcsb_entry": _rcsb_entry,
    "rcsb_download": _rcsb_download,
    "alphafold_prediction": _alphafold_prediction,
    "alphafold_download": _alphafold_download,
    "uniprot_search": _uniprot_search,
    "uniprot_entry": _uniprot_entry,
    "uniprot_download": _uniprot_download,
    "foldseek_databases": _foldseek_databases,
    "foldseek_submit": _foldseek_submit,
    "foldseek_status": _foldseek_status,
    "foldseek_result": _foldseek_result,
    "foldseek_download": _foldseek_download,
}


AIDD_BIO_TOOL_SPEC = {
    "name": "aidd_bio",
    "description": (
        "Search and fetch biomedical/protein structure information from RCSB PDB, "
        "AlphaFold DB, UniProt, and Foldseek. Use for AIDD work requiring protein "
        "metadata, experimental structures, predicted structures, sequences, or "
        "structure similarity search. Supports bounded previews of downloadable "
        "PDB/mmCIF/FASTA/JSON content."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": list(_OPERATIONS.keys()),
                "description": "Operation to execute.",
            },
            "query": {"type": "string", "description": "Search query."},
            "id": {"type": "string", "description": "RCSB PDB entry ID, e.g. 4HHB."},
            "entry_id": {
                "type": "string",
                "description": "Alias for RCSB PDB entry ID.",
            },
            "accession": {
                "type": "string",
                "description": "UniProt accession, e.g. P05067.",
            },
            "uniprot_accession": {
                "type": "string",
                "description": "Alias for UniProt accession.",
            },
            "ticket": {"type": "string", "description": "Foldseek ticket ID."},
            "entry": {"type": "integer", "description": "Foldseek result entry index."},
            "query_structure": {
                "type": "string",
                "description": "PDB or mmCIF structure text to submit to Foldseek.",
            },
            "databases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Foldseek database paths, e.g. ['afdb50', 'pdb100'].",
            },
            "mode": {
                "type": "string",
                "enum": ["3diaa", "tmalign", "lolalign"],
                "description": "Foldseek search mode. Default: 3diaa.",
            },
            "email": {
                "type": "string",
                "description": "Optional Foldseek notification email.",
            },
            "fields": {
                "type": "string",
                "description": "UniProt comma-separated fields.",
            },
            "file_format": {
                "type": "string",
                "enum": ["pdb", "cif", "bcif", "fasta", "json", "txt", "xml"],
                "description": "Download format for RCSB or UniProt.",
            },
            "file_type": {
                "type": "string",
                "enum": ["pdb", "cif", "bcif", "pae", "plddt", "msa"],
                "description": "AlphaFold downloadable file type.",
            },
            "return_type": {
                "type": "string",
                "enum": ["entry", "polymer_entity", "assembly"],
                "description": "RCSB search return type. Default: entry.",
            },
            "limit": {
                "type": "integer",
                "description": "Max result rows, default 5, max 25.",
            },
            "max_chars": {
                "type": "integer",
                "description": "Max text preview chars, max 50000.",
            },
        },
        "required": ["operation"],
        "additionalProperties": False,
    },
}


async def aidd_bio_handler(arguments: dict[str, Any]) -> tuple[str, bool]:
    operation = arguments.get("operation")
    if not operation:
        return "'operation' parameter is required.", False
    handler = _OPERATIONS.get(operation)
    if handler is None:
        return f"Unknown operation: {operation}. Valid: {', '.join(_OPERATIONS)}", False
    try:
        result = await handler(arguments)
        return result["formatted"], not result.get("isError", False)
    except httpx.HTTPStatusError as e:
        body = e.response.text[:500] if e.response is not None else ""
        return f"HTTP error: {e.response.status_code} — {body}", False
    except httpx.RequestError as e:
        return f"Request error: {e}", False
    except Exception as e:
        return f"Error in {operation}: {e}", False
