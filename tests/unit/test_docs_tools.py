import pytest

from agent.tools import docs_tools


@pytest.mark.asyncio
async def test_openapi_tool_spec_does_not_fetch_spec_at_startup(monkeypatch):
    async def fail_fetch():
        raise AssertionError("OpenAPI spec should be fetched only when tool runs")

    monkeypatch.setattr(docs_tools, "_fetch_openapi_spec", fail_fetch)

    spec = await docs_tools._get_api_search_tool_spec()

    assert spec["name"] == "find_hf_api"
    assert "enum" not in spec["parameters"]["properties"]["tag"]
