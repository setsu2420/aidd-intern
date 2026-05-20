import json
import subprocess
import sys
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


def test_builtin_tool_registration_keeps_heavy_tool_modules_lazy():
    script = """
import json
import sys

from agent.core.tools import create_builtin_tools

steps = []
steps.append("step 1: import create_builtin_tools")
tools = create_builtin_tools(local_mode=True)
steps.append(f"step 2: registered {len(tools)} local-mode tools")
loaded = sorted(
    name for name in (
        "agent.tools.docs_tools",
        "agent.tools.github_read_file",
        "whoosh",
        "nbconvert",
    )
    if name in sys.modules
)
steps.append(f"step 3: heavy modules loaded: {loaded}")
print(json.dumps({"steps": steps, "loaded": loaded}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["steps"][0] == "step 1: import create_builtin_tools"
    assert payload["steps"][1].startswith("step 2: registered ")
    assert payload["steps"][2] == "step 3: heavy modules loaded: []"
    assert payload["loaded"] == []
