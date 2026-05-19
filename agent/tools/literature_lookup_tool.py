"""Official literature lookup across preprint and publication metadata APIs.

The goal of this tool is to give the agent first-class paper metadata sources
without scraping publisher landing pages. In particular, bioRxiv/medRxiv
landing pages can be protected by Cloudflare, while their public API and
Europe PMC metadata remain accessible for normal research workflows.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from agent.tools.types import ToolResult

ARXIV_API_URL = "https://export.arxiv.org/api/query"
BIORXIV_API_URL = "https://api.biorxiv.org"
EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"

DEFAULT_LIMIT = 5
MAX_LIMIT = 20
MAX_ABSTRACT_CHARS = 1200
REQUEST_TIMEOUT = 25.0

SOURCE_ALIASES = {
    "all": "all",
    "arxiv": "arxiv",
    "bioarxiv": "biorxiv",
    "biorxiv": "biorxiv",
    "medrxiv": "medrxiv",
    "preprint": "preprints",
    "preprints": "preprints",
    "ppr": "preprints",
    "europepmc": "europe_pmc",
    "europe_pmc": "europe_pmc",
    "pmc": "pmc",
    "pubmed": "pubmed",
    "med": "pubmed",
    "crossref": "crossref",
}

DEFAULT_SOURCES = {"arxiv", "europe_pmc", "crossref"}

ARXIV_ID_RE = re.compile(
    r"^(?:arxiv:)?(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?$",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def _limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_LIMIT
    return max(1, min(parsed, MAX_LIMIT))


def _error(message: str) -> ToolResult:
    return {
        "formatted": message,
        "totalResults": 0,
        "resultsShared": 0,
        "isError": True,
    }


def _ok(formatted: str, total: int, shared: int | None = None) -> ToolResult:
    return {
        "formatted": formatted,
        "totalResults": total,
        "resultsShared": total if shared is None else shared,
    }


def _truncate(text: str | None, max_chars: int = MAX_ABSTRACT_CHARS) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split())


def _normalize_arxiv_id(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", text, flags=re.I)
    text = text.removeprefix("arXiv:").removeprefix("arxiv:")
    text = text.removesuffix(".pdf")
    return text.strip()


def _looks_like_arxiv_id(value: str) -> bool:
    return bool(ARXIV_ID_RE.match(_normalize_arxiv_id(value)))


def _normalize_doi(value: str) -> str | None:
    text = value.strip()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.I)
    text = text.removeprefix("doi:").removeprefix("DOI:")
    match = DOI_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;").strip()


def _parse_sources(raw: Any) -> set[str]:
    if raw is None or raw == "":
        return set(DEFAULT_SOURCES)
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in re.split(r"[,;\s]+", raw) if p.strip()]
    elif isinstance(raw, list):
        parts = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        parts = [str(raw).strip().lower()]

    mapped = {SOURCE_ALIASES.get(part, part) for part in parts}
    if "all" in mapped:
        return set(DEFAULT_SOURCES) | {"biorxiv", "medrxiv", "preprints"}
    return mapped or set(DEFAULT_SOURCES)


def _source_meta(record: dict[str, Any]) -> list[str]:
    meta = [record.get("source_label") or record.get("source") or "unknown"]
    if record.get("id"):
        meta.append(f"id: {record['id']}")
    if record.get("doi"):
        meta.append(f"doi: {record['doi']}")
    if record.get("date"):
        meta.append(f"date: {record['date']}")
    elif record.get("year"):
        meta.append(f"year: {record['year']}")
    if record.get("publisher"):
        meta.append(f"publisher: {record['publisher']}")
    return meta


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        key = (
            (record.get("doi") or "").lower()
            or (record.get("url") or "").lower()
            or f"{record.get('source')}:{record.get('id')}"
        )
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(record)
    return out


def _format_records(
    title: str, records: list[dict[str, Any]], errors: list[str]
) -> str:
    lines = [f"# {title}", f"Showing {len(records)} result(s)\n"]
    for idx, record in enumerate(records, 1):
        lines.append(f"## {idx}. {record.get('title') or '(untitled)'}")
        lines.append(" | ".join(_source_meta(record)))
        if record.get("url"):
            lines.append(record["url"])
        authors = record.get("authors")
        if authors:
            if isinstance(authors, list):
                author_text = ", ".join(str(a) for a in authors[:12])
                if len(authors) > 12:
                    author_text += f" (+{len(authors) - 12} more)"
            else:
                author_text = str(authors)
            lines.append(f"Authors: {author_text}")
        abstract = _truncate(_clean_text(record.get("abstract")))
        if abstract:
            lines.append(f"Abstract: {abstract}")
        links = record.get("links") or []
        if links:
            rendered = []
            for link in links[:4]:
                if isinstance(link, dict):
                    label = link.get("site") or link.get("documentStyle") or "link"
                    url = link.get("url")
                    if url:
                        rendered.append(f"{label}: {url}")
                elif isinstance(link, str):
                    rendered.append(link)
            if rendered:
                lines.append("Links: " + " | ".join(rendered))
        lines.append("")

    if errors:
        lines.append("## Source Warnings")
        for error in errors:
            lines.append(f"- {error}")

    lines.append(
        "Use `hf_papers` for Semantic Scholar citation graph/snippet search when an arXiv id is available."
    )
    return "\n".join(lines)


def _crossref_user_agent() -> str:
    email = os.environ.get("CROSSREF_MAILTO") or os.environ.get(
        "AIDD_INTERN_CONTACT_EMAIL"
    )
    if email:
        return f"aidd-intern/0.1 (mailto:{email})"
    return "aidd-intern/0.1"


async def _search_arxiv(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    *,
    by_id: bool = False,
) -> list[dict[str, Any]]:
    if by_id:
        params = {"id_list": _normalize_arxiv_id(query), "max_results": str(limit)}
    else:
        search_query = (
            query if re.search(r"\b(all|ti|au|abs|cat):", query) else f"all:{query}"
        )
        params = {
            "search_query": search_query,
            "start": "0",
            "max_results": str(limit),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    resp = await client.get(ARXIV_API_URL, params=params)
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.text)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    records: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        entry_url = entry.findtext("atom:id", default="", namespaces=ns).strip()
        arxiv_id = entry_url.rsplit("/", 1)[-1] if entry_url else ""
        title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        summary = _clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
        published = entry.findtext("atom:published", default="", namespaces=ns)
        doi = entry.findtext("arxiv:doi", default="", namespaces=ns).strip() or None
        authors = [
            _clean_text(author.findtext("atom:name", default="", namespaces=ns))
            for author in entry.findall("atom:author", ns)
        ]
        links = []
        for link in entry.findall("atom:link", ns):
            href = link.attrib.get("href")
            if href:
                links.append(
                    {
                        "site": link.attrib.get("title")
                        or link.attrib.get("type")
                        or "arXiv",
                        "url": href,
                    }
                )
        records.append(
            {
                "source": "arxiv",
                "source_label": "arXiv API",
                "id": arxiv_id,
                "doi": doi,
                "title": title,
                "authors": [a for a in authors if a],
                "abstract": summary,
                "date": published[:10] if published else "",
                "url": entry_url
                or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""),
                "links": links,
            }
        )
    return records


def _europe_pmc_filter_for_sources(sources: set[str]) -> str:
    filters: list[str] = []
    if sources & {"biorxiv", "medrxiv", "preprints"}:
        filters.append("SRC:PPR")
    if "pubmed" in sources:
        filters.append("SRC:MED")
    if "pmc" in sources:
        filters.append("IN_PMC:y")
    if not filters:
        return ""
    return " OR ".join(filters) if len(filters) > 1 else filters[0]


async def _search_europe_pmc(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    *,
    sources: set[str],
) -> list[dict[str, Any]]:
    source_filter = _europe_pmc_filter_for_sources(sources)
    if source_filter and not any(
        field in query.upper()
        for field in ("SRC:", "IN_PMC:", "DOI:", "PMCID:", "EXT_ID:")
    ):
        query = f"{query} {source_filter}"

    params = {
        "query": query,
        "format": "json",
        "pageSize": str(limit),
        "resultType": "core",
    }
    resp = await client.get(EUROPE_PMC_SEARCH_URL, params=params)
    resp.raise_for_status()
    payload = resp.json()
    records: list[dict[str, Any]] = []
    for row in (payload.get("resultList") or {}).get("result") or []:
        source = row.get("source") or ""
        source_label = {
            "PPR": "Europe PMC preprint index",
            "MED": "PubMed via Europe PMC",
            "PMC": "PubMed Central via Europe PMC",
        }.get(source, f"Europe PMC {source}" if source else "Europe PMC")
        book = row.get("bookOrReportDetails") or {}
        links = (row.get("fullTextUrlList") or {}).get("fullTextUrl") or []
        url = (
            f"https://europepmc.org/article/{source}/{row.get('id')}"
            if source and row.get("id")
            else ""
        )
        records.append(
            {
                "source": source.lower() if source else "europe_pmc",
                "source_label": source_label,
                "id": row.get("id"),
                "doi": row.get("doi"),
                "title": _clean_text(row.get("title")),
                "authors": row.get("authorString"),
                "abstract": row.get("abstractText"),
                "year": row.get("pubYear"),
                "date": row.get("firstPublicationDate") or "",
                "publisher": book.get("publisher"),
                "url": url,
                "links": links,
            }
        )
    return records


async def _search_crossref(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    doi = _normalize_doi(query)
    if doi:
        url = f"{CROSSREF_WORKS_URL}/{quote(doi, safe='')}"
        resp = await client.get(url, headers={"User-Agent": _crossref_user_agent()})
        resp.raise_for_status()
        items = [resp.json().get("message") or {}]
    else:
        params = {"query.bibliographic": query, "rows": str(limit)}
        resp = await client.get(
            CROSSREF_WORKS_URL,
            params=params,
            headers={"User-Agent": _crossref_user_agent()},
        )
        resp.raise_for_status()
        items = (resp.json().get("message") or {}).get("items") or []

    records: list[dict[str, Any]] = []
    for item in items:
        title = item.get("title") or []
        container = item.get("container-title") or []
        date_parts = (
            item.get("published-print")
            or item.get("published-online")
            or item.get("created")
            or {}
        ).get("date-parts") or []
        year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""
        authors = []
        for author in item.get("author") or []:
            name = " ".join(
                part for part in [author.get("given"), author.get("family")] if part
            )
            if name:
                authors.append(name)
        records.append(
            {
                "source": "crossref",
                "source_label": "Crossref REST API",
                "id": item.get("DOI"),
                "doi": item.get("DOI"),
                "title": _clean_text(title[0] if title else ""),
                "authors": authors,
                "abstract": item.get("abstract"),
                "year": year,
                "publisher": item.get("publisher")
                or (container[0] if container else ""),
                "url": item.get("URL")
                or (f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else ""),
                "links": [{"site": "DOI", "url": f"https://doi.org/{item.get('DOI')}"}]
                if item.get("DOI")
                else [],
            }
        )
    return records


async def _biorxiv_details(
    client: httpx.AsyncClient,
    doi: str,
    server: str,
) -> list[dict[str, Any]]:
    url = f"{BIORXIV_API_URL}/details/{server}/{doi}/na/json"
    resp = await client.get(url)
    resp.raise_for_status()
    payload = resp.json()
    return _parse_biorxiv_collection(
        payload.get("collection") or [], source_label=f"{server} API"
    )


async def _biorxiv_recent(
    client: httpx.AsyncClient,
    server: str,
    limit: int,
    *,
    date_from: str | None,
    date_to: str | None,
) -> list[dict[str, Any]]:
    if not date_to:
        date_to = date.today().isoformat()
    if not date_from:
        date_from = (date.fromisoformat(date_to) - timedelta(days=7)).isoformat()
    url = f"{BIORXIV_API_URL}/details/{server}/{date_from}/{date_to}/0/json"
    resp = await client.get(url)
    resp.raise_for_status()
    payload = resp.json()
    return _parse_biorxiv_collection(
        (payload.get("collection") or [])[:limit],
        source_label=f"{server} API",
    )


def _parse_biorxiv_collection(
    collection: list[dict[str, Any]],
    *,
    source_label: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in collection:
        server = (row.get("server") or source_label.split()[0] or "biorxiv").lower()
        doi = row.get("doi")
        links = []
        if row.get("jatsxml"):
            links.append({"site": "JATS XML", "url": row["jatsxml"]})
        if row.get("published"):
            links.append({"site": "Published version", "url": row["published"]})
        if doi:
            links.append({"site": "DOI", "url": f"https://doi.org/{doi}"})
        records.append(
            {
                "source": server,
                "source_label": source_label,
                "id": doi,
                "doi": doi,
                "title": _clean_text(row.get("title")),
                "authors": row.get("authors"),
                "abstract": row.get("abstract"),
                "date": row.get("date") or "",
                "publisher": row.get("category") or row.get("type"),
                "url": f"https://doi.org/{doi}" if doi else "",
                "links": links,
            }
        )
    return records


async def _op_search(args: dict[str, Any], limit: int) -> ToolResult:
    query = str(args.get("query") or args.get("identifier") or "").strip()
    if not query:
        return _error("'query' is required for search.")

    sources = _parse_sources(args.get("sources") or args.get("source"))
    tasks: list[tuple[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=True
    ) as client:
        if "arxiv" in sources:
            tasks.append(("arXiv", _search_arxiv(client, query, limit)))
        if sources & {"europe_pmc", "pmc", "pubmed", "biorxiv", "medrxiv", "preprints"}:
            tasks.append(
                (
                    "Europe PMC",
                    _search_europe_pmc(client, query, limit, sources=sources),
                )
            )
        if "crossref" in sources:
            tasks.append(("Crossref", _search_crossref(client, query, limit)))

        results = await asyncio.gather(
            *(task for _, task in tasks), return_exceptions=True
        )

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for (name, _), result in zip(tasks, results, strict=False):
        if isinstance(result, Exception):
            errors.append(f"{name}: {result}")
        else:
            records.extend(result)

    records = _dedupe_records(records)[:limit]
    if not records:
        return _ok(
            _format_records(f"Literature lookup for '{query}'", [], errors), 0, 0
        )
    return _ok(
        _format_records(f"Literature lookup for '{query}'", records, errors),
        total=len(records),
        shared=len(records),
    )


async def _op_details(args: dict[str, Any], limit: int) -> ToolResult:
    identifier = str(args.get("identifier") or args.get("query") or "").strip()
    if not identifier:
        return _error("'identifier' is required for details.")

    source = str(args.get("source") or "").strip().lower()
    server = SOURCE_ALIASES.get(source, source) if source else ""
    doi = _normalize_doi(identifier)
    records: list[dict[str, Any]] = []
    errors: list[str] = []

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=True
    ) as client:
        if _looks_like_arxiv_id(identifier) or server == "arxiv":
            try:
                records.extend(await _search_arxiv(client, identifier, 1, by_id=True))
            except Exception as exc:
                errors.append(f"arXiv: {exc}")
        if doi:
            biorxiv_servers = []
            if server in {"biorxiv", "bioarxiv", "medrxiv"}:
                biorxiv_servers = [server]
            elif doi.startswith("10.1101/"):
                biorxiv_servers = ["biorxiv", "medrxiv"]
            for bx_server in biorxiv_servers:
                try:
                    records.extend(await _biorxiv_details(client, doi, bx_server))
                    if records:
                        break
                except Exception as exc:
                    errors.append(f"{bx_server}: {exc}")
            try:
                records.extend(
                    await _search_europe_pmc(
                        client, f"DOI:{doi}", limit, sources={"europe_pmc"}
                    )
                )
            except Exception as exc:
                errors.append(f"Europe PMC: {exc}")
            try:
                records.extend(await _search_crossref(client, doi, 1))
            except Exception as exc:
                errors.append(f"Crossref: {exc}")
        elif not records:
            try:
                records.extend(
                    await _search_europe_pmc(
                        client,
                        identifier,
                        limit,
                        sources={"europe_pmc", "pmc", "pubmed", "preprints"},
                    )
                )
            except Exception as exc:
                errors.append(f"Europe PMC: {exc}")

    records = _dedupe_records(records)[:limit]
    return _ok(
        _format_records(f"Literature details for '{identifier}'", records, errors),
        total=len(records),
        shared=len(records),
    )


async def _op_recent_preprints(args: dict[str, Any], limit: int) -> ToolResult:
    raw_server = str(args.get("server") or args.get("source") or "biorxiv").lower()
    server = SOURCE_ALIASES.get(raw_server, raw_server)
    if server not in {"biorxiv", "medrxiv"}:
        return _error("recent_preprints source/server must be biorxiv or medrxiv.")

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=True
    ) as client:
        try:
            records = await _biorxiv_recent(
                client,
                server,
                limit,
                date_from=args.get("date_from"),
                date_to=args.get("date_to"),
            )
        except Exception as exc:
            return _error(f"{server} API failed: {exc}")

    return _ok(
        _format_records(f"Recent {server} preprints", records, []),
        total=len(records),
        shared=len(records),
    )


_OPERATIONS = {
    "search": _op_search,
    "details": _op_details,
    "recent_preprints": _op_recent_preprints,
}


LITERATURE_LOOKUP_TOOL_SPEC = {
    "name": "literature_lookup",
    "description": (
        "Search and fetch paper metadata from official APIs: arXiv export API, "
        "bioRxiv/medRxiv API, Europe PMC/PubMed/PMC, and Crossref. Use this "
        "instead of scraping publisher or preprint landing pages when bioRxiv, "
        "medRxiv, arXiv, PubMed, PMC, DOI, or general literature metadata is needed. "
        "It is the safe path around Cloudflare-protected landing pages: fetch "
        "the public metadata/API records, then cite the source links."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": list(_OPERATIONS.keys()),
                "description": "Operation to run: search, details, or recent_preprints.",
            },
            "query": {
                "type": "string",
                "description": "Keyword/title/DOI query for search. Examples: 'PPIFlow', 'PD-L1 binder design'.",
            },
            "identifier": {
                "type": "string",
                "description": "DOI, arXiv id, PMID/PMCID/PPR id, or other known paper identifier for details.",
            },
            "sources": {
                "type": "string",
                "description": (
                    "Comma-separated source list for search. Supported: arxiv, biorxiv, medrxiv, "
                    "preprints, europe_pmc, pubmed, pmc, crossref, all. Default: arxiv,europe_pmc,crossref."
                ),
            },
            "source": {
                "type": "string",
                "description": "Single source hint for details or recent_preprints, e.g. arxiv, biorxiv, medrxiv.",
            },
            "server": {
                "type": "string",
                "enum": ["biorxiv", "medrxiv"],
                "description": "bioRxiv API server for recent_preprints. Default: biorxiv.",
            },
            "date_from": {
                "type": "string",
                "description": "YYYY-MM-DD start date for recent_preprints. Defaults to 7 days before date_to.",
            },
            "date_to": {
                "type": "string",
                "description": "YYYY-MM-DD end date for recent_preprints. Defaults to today.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum records returned. Default 5, max 20.",
            },
        },
        "required": ["operation"],
    },
}


async def literature_lookup_handler(arguments: dict[str, Any]) -> tuple[str, bool]:
    operation = arguments.get("operation")
    if not operation:
        return "'operation' parameter is required.", False
    handler = _OPERATIONS.get(operation)
    if not handler:
        return f"Unknown operation: {operation}. Valid: {', '.join(_OPERATIONS)}", False

    limit = _limit(arguments.get("limit"))
    try:
        result = await handler(arguments, limit)
        return result["formatted"], not result.get("isError", False)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:200] if exc.response is not None else ""
        return f"API error: {exc.response.status_code} {body}", False
    except httpx.RequestError as exc:
        return f"Request error: {exc}", False
    except Exception as exc:
        return f"Error in {operation}: {exc}", False
