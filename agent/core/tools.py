"""
Tool system for the agent
Provides ToolSpec and ToolRouter for managing both built-in and MCP tools
"""

import ast
import importlib
import importlib.util
import logging
import os
import warnings
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import EmbeddedResource, ImageContent, TextContent

from agent.config import MCPServerConfig

# NOTE: Private HF repo tool disabled - replaced by hf_repo_files and hf_repo_git
# from agent.tools.private_hf_repo_tools import (
#     PRIVATE_HF_REPO_TOOL_SPEC,
#     private_hf_repo_handler,
# )

# Suppress aiohttp deprecation warning
warnings.filterwarnings(
    "ignore", category=DeprecationWarning, module="aiohttp.connector"
)

logger = logging.getLogger(__name__)

NOT_ALLOWED_TOOL_NAMES = ["hf_jobs", "hf_doc_search", "hf_doc_fetch", "hf_whoami"]
HF_MCP_SERVER_NAME = "hf-mcp-server"
PROTEIN_MCP_SERVER_PREFIX = "proteinmcp-"
_UNRESOLVED = object()

_OPENAPI_SEARCH_TOOL_SPEC = {
    "name": "find_hf_api",
    "description": (
        "Find HuggingFace Hub REST API endpoints to make HTTP requests. Returns curl examples with authentication. "
        "USE THIS TOOL when you need to call the HF Hub API directly - for operations like: "
        "uploading/downloading files, managing repos, listing models/datasets, getting user info, "
        "managing webhooks, collections, discussions, or any Hub interaction not covered by other tools. "
        "**Use cases:** (1) 'Stream Space logs' -> query='space logs', "
        "(2) 'Get Space metrics/Zero-GPU usage' -> query='space metrics', "
        "(3) 'List organization members' -> query='organization members', "
        "(4) 'Generate repo access token' -> query='jwt token', "
        "(5) 'Check repo security scan' -> query='security scan'. "
        "**Search modes:** Use 'query' for keyword search, 'tag' to browse a category, or both. "
        "If query finds no results, falls back to showing all endpoints in the tag. "
        "**Output:** Full endpoint details with method, path, parameters, curl command, and response schema."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Keyword search across endpoint summaries, descriptions, and operation IDs. "
                    "Examples: 'upload file', 'create repository', 'list user models', 'delete branch', "
                    "'webhook', 'collection', 'discussion comments'. Supports stemming (upload/uploading both work)."
                ),
            },
            "tag": {
                "type": "string",
                "description": (
                    "Optional API category tag. Use alone to browse all endpoints in a category, "
                    "or combine with 'query' to search within a category. Examples: models, "
                    "datasets, spaces, collections, webhooks, organizations."
                ),
            },
        },
        "required": [],
    },
}
_PROTEIN_DESIGN_TOOL_SPECS = [
    {
        "name": "run_pxdesign",
        "description": (
            "Generate protein binders using PXdesign DiT backbone diffusion "
            "and ProteinMPNN sequence design."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_pdb": {
                    "type": "string",
                    "description": "Path to target PDB file.",
                },
                "interface_residues": {
                    "type": "string",
                    "description": "Comma-separated target interface residue indices.",
                },
                "num_samples": {"type": "integer", "default": 100},
                "tool_runtime": {
                    "type": "string",
                    "enum": ["local", "sandbox"],
                    "default": "local",
                },
            },
            "required": ["target_pdb", "interface_residues"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_pxdesign_tool",
    },
    {
        "name": "run_boltzgen",
        "description": "Generate binders under topological constraints using BoltzGen.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_pdb": {"type": "string"},
                "constraints_json": {
                    "type": "string",
                    "description": "JSON serialized geometric constraints.",
                },
                "num_samples": {"type": "integer", "default": 100},
                "tool_runtime": {
                    "type": "string",
                    "enum": ["local", "sandbox"],
                    "default": "local",
                },
            },
            "required": ["target_pdb", "constraints_json"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_boltzgen_tool",
    },
    {
        "name": "run_bindcraft",
        "description": "Run multi-round automated binder optimization via BindCraft.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_pdb": {"type": "string"},
                "binder_length": {
                    "type": "integer",
                    "description": "Target binder length in amino acids.",
                },
                "iterations": {"type": "integer", "default": 50},
                "output_dir": {
                    "type": "string",
                    "description": "Directory for BindCraft outputs.",
                },
                "binder_name": {
                    "type": "string",
                    "description": "Prefix for generated binder designs.",
                },
                "target_chains": {
                    "type": "string",
                    "default": "A",
                    "description": "Target chain IDs for interface design.",
                },
                "hotspot_residues": {
                    "type": "string",
                    "description": "Comma-separated target hotspot residue numbers.",
                },
                "num_designs": {
                    "type": "integer",
                    "default": 1,
                    "description": "Number of final accepted designs to request.",
                },
                "max_trajectories": {
                    "type": "integer",
                    "description": "Optional cap on attempted BindCraft trajectories.",
                },
                "device": {
                    "type": "integer",
                    "description": "GPU index to use. Defaults to the GPU with most free memory.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Optional command timeout in seconds.",
                },
                "tool_runtime": {
                    "type": "string",
                    "enum": ["local", "sandbox"],
                    "default": "local",
                },
            },
            "required": ["target_pdb", "binder_length"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_bindcraft_tool",
    },
]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _module_path(module_name: str) -> str | None:
    spec = importlib.util.find_spec(module_name)
    return spec.origin if spec and spec.origin else None


def _resolve_static_name(name: str, constants: dict[str, Any]) -> Any:
    if name in constants:
        return constants[name]
    if name.endswith("_OPERATIONS"):
        return []
    return _UNRESOLVED


def _literal_from_ast(node: ast.AST, constants: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            resolved = _literal_from_ast(value, constants)
            if resolved is _UNRESOLVED:
                return _UNRESOLVED
            parts.append(str(resolved))
        return "".join(parts)
    if isinstance(node, ast.FormattedValue):
        return _literal_from_ast(node.value, constants)
    if isinstance(node, ast.Dict):
        result = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                return _UNRESOLVED
            key = _literal_from_ast(key_node, constants)
            value = _literal_from_ast(value_node, constants)
            if key is _UNRESOLVED or value is _UNRESOLVED:
                return _UNRESOLVED
            result[key] = value
        return result
    if isinstance(node, ast.List):
        values = [_literal_from_ast(item, constants) for item in node.elts]
        if any(value is _UNRESOLVED for value in values):
            return _UNRESOLVED
        return values
    if isinstance(node, ast.Tuple):
        values = [_literal_from_ast(item, constants) for item in node.elts]
        if any(value is _UNRESOLVED for value in values):
            return _UNRESOLVED
        return tuple(values)
    if isinstance(node, ast.Set):
        values = [_literal_from_ast(item, constants) for item in node.elts]
        if any(value is _UNRESOLVED for value in values):
            return _UNRESOLVED
        return set(values)
    if isinstance(node, ast.Name):
        return _resolve_static_name(node.id, constants)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_from_ast(node.left, constants)
        right = _literal_from_ast(node.right, constants)
        if left is _UNRESOLVED or right is _UNRESOLVED:
            return _UNRESOLVED
        return left + right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "list" and len(node.args) == 1 and not node.keywords:
            value = _literal_from_ast(node.args[0], constants)
            if value is _UNRESOLVED:
                return _UNRESOLVED
            if isinstance(value, dict):
                return list(value.keys())
            return list(value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "keys" and not node.args and not node.keywords:
            value = _literal_from_ast(node.func.value, constants)
            if isinstance(value, dict):
                return list(value.keys())
    return _UNRESOLVED


def _dict_with_static_keys(node: ast.AST) -> dict[str, None] | None:
    if not isinstance(node, ast.Dict):
        return None
    keys: dict[str, None] = {}
    for key_node in node.keys:
        if key_node is None:
            return None
        try:
            key = ast.literal_eval(key_node)
        except Exception:
            return None
        if not isinstance(key, str):
            return None
        keys[key] = None
    return keys


def _static_tool_spec_from_source(module_name: str, spec_attr: str) -> dict[str, Any]:
    path = _module_path(module_name)
    if not path:
        raise ValueError(f"Could not locate module {module_name}")

    with open(path, encoding="utf-8") as source_file:
        tree = ast.parse(source_file.read(), filename=path)

    constants: dict[str, Any] = {}
    wanted_node: ast.AST | None = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        value = _literal_from_ast(node.value, constants)
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == spec_attr:
                wanted_node = node.value
            if target.id.isupper() and value is not _UNRESOLVED:
                constants[target.id] = value
            elif target.id.isupper():
                keyed_dict = _dict_with_static_keys(node.value)
                if keyed_dict is not None:
                    constants[target.id] = keyed_dict

    if wanted_node is None:
        raise ValueError(f"{spec_attr} not found in {module_name}")

    spec = _literal_from_ast(wanted_node, constants)
    if spec is _UNRESOLVED:
        raise ValueError(f"{spec_attr} in {module_name} is not statically readable")
    if not isinstance(spec, dict):
        raise TypeError(f"{spec_attr} in {module_name} is not a dict")
    return spec


def _handler_params_from_source(
    module_name: str, handler_attr: str
) -> tuple[set[str], bool]:
    path = _module_path(module_name)
    if not path:
        return set(), False
    try:
        with open(path, encoding="utf-8") as source_file:
            tree = ast.parse(source_file.read(), filename=path)
    except Exception:
        return set(), False

    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name != handler_attr:
            continue
        args = node.args
        names = {arg.arg for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
        return names, args.kwarg is not None
    return set(), False


def _mcp_server_enabled_for_startup(
    name: str,
    *,
    hf_token: str | None,
) -> bool:
    if name == HF_MCP_SERVER_NAME:
        # The Hugging Face MCP endpoint requires auth. Without a token, FastMCP
        # spends startup time on a doomed connection and may print a 401
        # traceback into the TUI.
        return bool(hf_token)
    if name.startswith(PROTEIN_MCP_SERVER_PREFIX):
        # ProteinMCP launchers clone/check local repos and start Python stdio
        # servers. Keep that cost out of the default startup path unless the
        # user explicitly enables them.
        return _env_bool("AIDD_INTERN_ENABLE_PROTEINMCP")
    return True


def filter_startup_mcp_servers(
    mcp_servers: dict[str, MCPServerConfig],
    *,
    hf_token: str | None,
) -> dict[str, MCPServerConfig]:
    """Return MCP servers that should be connected during cold start."""
    return {
        name: server
        for name, server in mcp_servers.items()
        if _mcp_server_enabled_for_startup(name, hf_token=hf_token)
    }


def convert_mcp_content_to_string(content: list) -> str:
    """
    Convert MCP content blocks to a string format compatible with LLM messages.

    Based on FastMCP documentation, content can be:
    - TextContent: has .text field
    - ImageContent: has .data and .mimeType fields
    - EmbeddedResource: has .resource field with .text or .blob

    Args:
        content: List of MCP content blocks

    Returns:
        String representation of the content suitable for LLM consumption
    """
    if not content:
        return ""

    parts = []
    for item in content:
        if isinstance(item, TextContent):
            # Extract text from TextContent blocks
            parts.append(item.text)
        elif isinstance(item, ImageContent):
            # TODO: Handle images
            # For images, include a description with MIME type
            parts.append(f"[Image: {item.mimeType}]")
        elif isinstance(item, EmbeddedResource):
            # TODO: Handle embedded resources
            # For embedded resources, try to extract text
            resource = item.resource
            if hasattr(resource, "text") and resource.text:
                parts.append(resource.text)
            elif hasattr(resource, "blob") and resource.blob:
                parts.append(
                    f"[Binary data: {resource.mimeType if hasattr(resource, 'mimeType') else 'unknown'}]"
                )
            else:
                parts.append(
                    f"[Resource: {resource.uri if hasattr(resource, 'uri') else 'unknown'}]"
                )
        else:
            # Fallback: try to convert to string
            parts.append(str(item))

    return "\n".join(parts)


@dataclass
class ToolSpec:
    """Tool specification for LLM"""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Optional[Callable[[dict[str, Any]], Awaitable[tuple[str, bool]]]] = None


def _lazy_handler(module_name: str, attr_name: str) -> Callable[..., Awaitable]:
    async def _handler(*args: Any, **kwargs: Any) -> tuple[str, bool]:
        module = importlib.import_module(module_name)
        handler = getattr(module, attr_name)
        return await handler(*args, **kwargs)

    params, accepts_kwargs = _handler_params_from_source(module_name, attr_name)
    _handler._tool_param_names = params  # type: ignore[attr-defined]
    _handler._tool_accepts_kwargs = accepts_kwargs  # type: ignore[attr-defined]
    return _handler


def _tool_spec_from_module(
    module_name: str,
    spec_attr: str,
    handler_attr: str,
) -> ToolSpec:
    try:
        spec = _static_tool_spec_from_source(module_name, spec_attr)
    except Exception as exc:
        logger.debug(
            "Falling back to importing %s for %s: %s", module_name, spec_attr, exc
        )
        module = importlib.import_module(module_name)
        spec = getattr(module, spec_attr)
    return ToolSpec(
        name=spec["name"],
        description=spec["description"],
        parameters=spec["parameters"],
        handler=_lazy_handler(module_name, handler_attr),
    )


class ToolRouter:
    """
    Routes tool calls to appropriate handlers.
    Based on codex-rs/core/src/tools/router.rs
    """

    def __init__(
        self,
        mcp_servers: dict[str, MCPServerConfig],
        hf_token: str | None = None,
        local_mode: bool = False,
    ):
        self.tools: dict[str, ToolSpec] = {}
        self.mcp_servers: dict[str, dict[str, Any]] = {}

        for tool in create_builtin_tools(local_mode=local_mode):
            self.register_tool(tool)

        self.mcp_client: Client | None = None
        active_mcp_servers = filter_startup_mcp_servers(
            mcp_servers,
            hf_token=hf_token,
        )
        if active_mcp_servers:
            mcp_servers_payload = {}
            for name, server in active_mcp_servers.items():
                data = server.model_dump()
                if hf_token and not data.get("auth"):
                    headers = dict(data.get("headers") or {})
                    headers["Authorization"] = f"Bearer {hf_token}"
                    data["headers"] = headers
                mcp_servers_payload[name] = data
            self.mcp_servers = mcp_servers_payload
            self.mcp_client = Client({"mcpServers": mcp_servers_payload})
        self._mcp_initialized = False

    def register_tool(self, tool: ToolSpec) -> None:
        self.tools[tool.name] = tool

    async def register_mcp_tools(self) -> None:
        tools = await self.mcp_client.list_tools()
        registered_names = []
        skipped_count = 0
        for tool in tools:
            if tool.name in NOT_ALLOWED_TOOL_NAMES:
                skipped_count += 1
                continue
            registered_names.append(tool.name)
            self.register_tool(
                ToolSpec(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.inputSchema,
                    handler=None,
                )
            )
        logger.info(
            f"Loaded {len(registered_names)} MCP tools: {', '.join(registered_names)} ({skipped_count} disabled)"
        )

    async def register_openapi_tool(self) -> None:
        """Register the OpenAPI search tool (requires async initialization)"""
        openapi_spec = _OPENAPI_SEARCH_TOOL_SPEC
        self.register_tool(
            ToolSpec(
                name=openapi_spec["name"],
                description=openapi_spec["description"],
                parameters=openapi_spec["parameters"],
                handler=_lazy_handler(
                    "agent.tools.docs_tools", "search_openapi_handler"
                ),
            )
        )
        logger.info(f"Loaded OpenAPI search tool: {openapi_spec['name']}")

    def get_tool_specs_for_llm(self) -> list[dict[str, Any]]:
        """Get tool specifications in OpenAI format"""
        specs = []
        for tool in self.tools.values():
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return specs

    async def __aenter__(self) -> "ToolRouter":
        if self.mcp_client is not None:
            try:
                await self.mcp_client.__aenter__()
                await self.mcp_client.initialize()
                await self.register_mcp_tools()
                self._mcp_initialized = True
            except Exception as e:
                logger.warning(
                    "MCP connection failed, continuing without MCP tools: %s", e
                )
                self.mcp_client = None

        await self.register_openapi_tool()

        total_tools = len(self.tools)
        logger.info(f"Agent ready with {total_tools} tools total")

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.mcp_client is not None:
            await self.mcp_client.__aexit__(exc_type, exc, tb)
            self._mcp_initialized = False

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session: Any = None,
        tool_call_id: str | None = None,
    ) -> tuple[str, bool]:
        """
        Call a tool and return (output_string, success_bool).

        For MCP tools, converts the CallToolResult content blocks to a string.
        For built-in tools, calls their handler directly.
        """
        # Check if this is a built-in tool with a handler
        tool = self.tools.get(tool_name)
        if tool and tool.handler:
            # Check if handler accepts session argument
            params = getattr(tool.handler, "_tool_param_names", None)
            accepts_kwargs = getattr(tool.handler, "_tool_accepts_kwargs", False)
            if params is None:
                import inspect

                params = set(inspect.signature(tool.handler).parameters)
            if "session" in params or accepts_kwargs:
                # Check if handler also accepts tool_call_id parameter
                if "tool_call_id" in params or accepts_kwargs:
                    return await tool.handler(
                        arguments, session=session, tool_call_id=tool_call_id
                    )
                return await tool.handler(arguments, session=session)
            return await tool.handler(arguments)

        # Otherwise, use MCP client
        if self._mcp_initialized:
            try:
                result = await self.mcp_client.call_tool(tool_name, arguments)
                output = convert_mcp_content_to_string(result.content)
                return output, not result.is_error
            except ToolError as e:
                # Catch MCP tool errors and return them to the agent
                error_msg = f"Tool error: {str(e)}"
                return error_msg, False

        return "MCP client not initialized", False


# ============================================================================
# BUILT-IN TOOL HANDLERS
# ============================================================================


def create_builtin_tools(local_mode: bool = False) -> list[ToolSpec]:
    """Create built-in tool specifications"""
    # in order of importance
    tools = [
        _tool_spec_from_module(
            "agent.tools.research_tool", "RESEARCH_TOOL_SPEC", "research_handler"
        ),
        _tool_spec_from_module(
            "agent.tools.docs_tools",
            "EXPLORE_HF_DOCS_TOOL_SPEC",
            "explore_hf_docs_handler",
        ),
        _tool_spec_from_module(
            "agent.tools.docs_tools", "HF_DOCS_FETCH_TOOL_SPEC", "hf_docs_fetch_handler"
        ),
        _tool_spec_from_module(
            "agent.tools.literature_lookup_tool",
            "LITERATURE_LOOKUP_TOOL_SPEC",
            "literature_lookup_handler",
        ),
        _tool_spec_from_module(
            "agent.tools.papers_tool", "HF_PAPERS_TOOL_SPEC", "hf_papers_handler"
        ),
        _tool_spec_from_module(
            "agent.tools.web_search_tool", "WEB_SEARCH_TOOL_SPEC", "web_search_handler"
        ),
        _tool_spec_from_module(
            "agent.tools.aidd_bio_tool", "AIDD_BIO_TOOL_SPEC", "aidd_bio_handler"
        ),
        _tool_spec_from_module(
            "agent.tools.dataset_tools",
            "HF_INSPECT_DATASET_TOOL_SPEC",
            "hf_inspect_dataset_handler",
        ),
        _tool_spec_from_module(
            "agent.tools.plan_tool", "PLAN_TOOL_SPEC", "plan_tool_handler"
        ),
        _tool_spec_from_module(
            "agent.tools.role_handoff_tool",
            "ROLE_HANDOFF_TOOL_SPEC",
            "role_handoff_handler",
        ),
        _tool_spec_from_module(
            "agent.tools.notify_tool", "NOTIFY_TOOL_SPEC", "notify_handler"
        ),
        _tool_spec_from_module(
            "agent.tools.jobs_tool", "HF_JOBS_TOOL_SPEC", "hf_jobs_handler"
        ),
        _tool_spec_from_module(
            "agent.tools.hf_repo_files_tool",
            "HF_REPO_FILES_TOOL_SPEC",
            "hf_repo_files_handler",
        ),
        _tool_spec_from_module(
            "agent.tools.hf_repo_git_tool",
            "HF_REPO_GIT_TOOL_SPEC",
            "hf_repo_git_handler",
        ),
        _tool_spec_from_module(
            "agent.tools.github_find_examples",
            "GITHUB_FIND_EXAMPLES_TOOL_SPEC",
            "github_find_examples_handler",
        ),
        _tool_spec_from_module(
            "agent.tools.github_list_repos",
            "GITHUB_LIST_REPOS_TOOL_SPEC",
            "github_list_repos_handler",
        ),
        _tool_spec_from_module(
            "agent.tools.github_read_file",
            "GITHUB_READ_FILE_TOOL_SPEC",
            "github_read_file_handler",
        ),
        _tool_spec_from_module(
            "agent.tools.binder_design_tool",
            "BINDER_DESIGN_TOOL_SPEC",
            "binder_design_handler",
        ),
        _tool_spec_from_module(
            "agent.workflows.protein_design.ace",
            "ACE_PLAYBOOK_TOOL_SPEC",
            "ace_playbook_handler",
        ),
    ]
    tools.extend(
        ToolSpec(
            name=spec["name"],
            description=spec["description"],
            parameters=spec["parameters"],
            handler=_lazy_handler(spec["module"], spec["handler"]),
        )
        for spec in _PROTEIN_DESIGN_TOOL_SPECS
    )

    # Sandbox or local tools (highest priority)
    if local_mode:
        from agent.tools.local_tools import get_local_tools

        tools = get_local_tools() + tools
    else:
        from agent.tools.sandbox_tool import get_sandbox_tools

        tools = get_sandbox_tools() + tools

    tool_names = ", ".join([t.name for t in tools])
    logger.info(f"Loaded {len(tools)} built-in tools: {tool_names}")

    return tools
