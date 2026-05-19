from types import SimpleNamespace

from agent.core import tools as tools_module
from agent.core.tools import ToolRouter, filter_startup_mcp_servers


def _server(**data):
    return SimpleNamespace(model_dump=lambda: dict(data))


def test_startup_filters_optional_mcp_servers_without_token(monkeypatch):
    monkeypatch.delenv("AIDD_INTERN_ENABLE_PROTEINMCP", raising=False)
    servers = {
        "hf-mcp-server": _server(transport="http", url="https://hf.co/mcp"),
        "proteinmcp-bindcraft": _server(transport="stdio", command="bash"),
        "custom": _server(transport="http", url="http://127.0.0.1/mcp"),
    }

    active = filter_startup_mcp_servers(
        servers, hf_token=None, domain_pack="aidd_binder"
    )

    assert set(active) == {"custom"}


def test_startup_enables_authenticated_hf_and_protein_design_mcp(monkeypatch):
    monkeypatch.delenv("AIDD_INTERN_ENABLE_PROTEINMCP", raising=False)
    servers = {
        "hf-mcp-server": _server(transport="http", url="https://hf.co/mcp"),
        "proteinmcp-bindcraft": _server(transport="stdio", command="bash"),
        "custom": _server(transport="http", url="http://127.0.0.1/mcp"),
    }

    active = filter_startup_mcp_servers(
        servers, hf_token="hf-token", domain_pack="protein_design"
    )

    assert set(active) == {"hf-mcp-server", "proteinmcp-bindcraft", "custom"}


def test_tool_router_does_not_construct_mcp_client_when_all_servers_skipped(
    monkeypatch,
):
    monkeypatch.delenv("AIDD_INTERN_ENABLE_PROTEINMCP", raising=False)

    def fail_client(*_args, **_kwargs):
        raise AssertionError("MCP client should not be constructed")

    monkeypatch.setattr(tools_module, "Client", fail_client)

    router = ToolRouter(
        {
            "hf-mcp-server": _server(transport="http", url="https://hf.co/mcp"),
            "proteinmcp-bindcraft": _server(transport="stdio", command="bash"),
        },
        hf_token=None,
        local_mode=True,
        domain_pack="aidd_binder",
    )

    assert router.mcp_client is None


def test_tool_router_forwards_hf_token_as_bearer_header(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, payload):
            seen["payload"] = payload

    monkeypatch.setattr(tools_module, "Client", FakeClient)

    ToolRouter(
        {"hf-mcp-server": _server(transport="http", url="https://hf.co/mcp")},
        hf_token="hf-token",
        local_mode=True,
        domain_pack="aidd_binder",
    )

    config = seen["payload"]["mcpServers"]["hf-mcp-server"]
    assert config["headers"]["Authorization"] == "Bearer hf-token"
