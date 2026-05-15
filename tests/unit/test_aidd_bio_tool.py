import pytest

from agent.core.tools import create_builtin_tools
from agent.tools import aidd_bio_tool


@pytest.mark.asyncio
async def test_aidd_bio_rcsb_search_posts_full_text_payload(monkeypatch):
    seen = {}

    async def fake_post_json(url, payload, **kwargs):
        seen["url"] = url
        seen["payload"] = payload
        seen["kwargs"] = kwargs
        return {
            "total_count": 2,
            "result_set": [
                {"identifier": "4HHB", "score": 1.0},
                {"identifier": "1A3N", "score": 0.8},
            ],
        }

    monkeypatch.setattr(aidd_bio_tool, "_post_json", fake_post_json)

    text, ok = await aidd_bio_tool.aidd_bio_handler(
        {"operation": "rcsb_search", "query": "hemoglobin", "limit": 2}
    )

    assert ok is True
    assert seen["url"] == aidd_bio_tool.RCSB_SEARCH_URL
    assert seen["payload"]["query"]["service"] == "full_text"
    assert seen["payload"]["query"]["parameters"]["value"] == "hemoglobin"
    assert seen["payload"]["request_options"]["paginate"]["rows"] == 2
    assert "4HHB" in text
    assert "https://www.rcsb.org/structure/4HHB" in text


@pytest.mark.asyncio
async def test_aidd_bio_alphafold_prediction_formats_download_links(monkeypatch):
    async def fake_get_json(url, **kwargs):
        assert url == f"{aidd_bio_tool.ALPHAFOLD_API_URL}/prediction/P05067"
        return [
            {
                "entryId": "AF-P05067-F1",
                "uniprotAccession": "P05067",
                "uniprotId": "A4_HUMAN",
                "uniprotDescription": "Amyloid-beta precursor protein",
                "organismScientificName": "Homo sapiens",
                "globalMetricValue": 67.38,
                "pdbUrl": "https://example.test/model.pdb",
                "cifUrl": "https://example.test/model.cif",
                "paeDocUrl": "https://example.test/pae.json",
            }
        ]

    monkeypatch.setattr(aidd_bio_tool, "_get_json", fake_get_json)

    text, ok = await aidd_bio_tool.aidd_bio_handler(
        {"operation": "alphafold_prediction", "accession": "P05067"}
    )

    assert ok is True
    assert "AF-P05067-F1" in text
    assert "Amyloid-beta precursor protein" in text
    assert "https://example.test/model.pdb" in text


@pytest.mark.asyncio
async def test_aidd_bio_uniprot_search_formats_protein_records(monkeypatch):
    async def fake_get_json(url, **kwargs):
        assert url == f"{aidd_bio_tool.UNIPROT_API_URL}/search"
        assert kwargs["params"]["query"] == "insulin"
        assert kwargs["params"]["format"] == "json"
        return {
            "results": [
                {
                    "primaryAccession": "P01308",
                    "uniProtkbId": "INS_HUMAN",
                    "proteinDescription": {
                        "recommendedName": {"fullName": {"value": "Insulin"}}
                    },
                    "genes": [{"geneName": {"value": "INS"}}],
                    "organism": {"scientificName": "Homo sapiens"},
                    "sequence": {"length": 110},
                }
            ]
        }

    monkeypatch.setattr(aidd_bio_tool, "_get_json", fake_get_json)

    text, ok = await aidd_bio_tool.aidd_bio_handler(
        {"operation": "uniprot_search", "query": "insulin", "limit": 1}
    )

    assert ok is True
    assert "P01308" in text
    assert "Insulin" in text
    assert "https://www.uniprot.org/uniprotkb/P01308" in text


@pytest.mark.asyncio
async def test_aidd_bio_foldseek_submit_posts_structure_file(monkeypatch):
    seen = {}

    async def fake_post_form(url, data, query):
        seen["url"] = url
        seen["data"] = data
        seen["query"] = query
        return {"id": "ticket-123", "status": "PENDING"}

    monkeypatch.setattr(aidd_bio_tool, "_foldseek_post_form", fake_post_form)

    text, ok = await aidd_bio_tool.aidd_bio_handler(
        {
            "operation": "foldseek_submit",
            "query_structure": "HEADER TEST\nATOM ...",
            "databases": ["afdb50", "pdb100"],
        }
    )

    assert ok is True
    assert seen["url"] == f"{aidd_bio_tool.FOLDSEEK_URL}/api/ticket"
    assert ("mode", "3diaa") in seen["data"]
    assert ("database[]", "afdb50") in seen["data"]
    assert ("database[]", "pdb100") in seen["data"]
    assert seen["query"].startswith("HEADER TEST")
    assert "ticket-123" in text
    assert "foldseek_status" in text


@pytest.mark.asyncio
async def test_aidd_bio_handler_reports_missing_or_unknown_operation():
    text, ok = await aidd_bio_tool.aidd_bio_handler({})
    assert ok is False
    assert "'operation' parameter is required" in text

    text, ok = await aidd_bio_tool.aidd_bio_handler({"operation": "nope"})
    assert ok is False
    assert "Unknown operation" in text


def test_aidd_bio_is_registered_for_llm():
    tools = create_builtin_tools(local_mode=True)
    specs = {tool.name: tool for tool in tools}

    assert "aidd_bio" in specs
    assert (
        "rcsb_search" in specs["aidd_bio"].parameters["properties"]["operation"]["enum"]
    )
