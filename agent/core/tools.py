"""
Tool system for the agent
Provides ToolSpec and ToolRouter for managing both built-in and MCP tools
"""

import asyncio
import ast
import importlib
import importlib.util
import json as _json
import logging
import os
import re
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

# ═══════════════════════════════════════════════════════════════════════
# Pre-compiled regex patterns for security checks (module-level caching)
# ═══════════════════════════════════════════════════════════════════════

# Command injection patterns (pre-compiled for performance)
_INJECTION_PATTERNS = [
    re.compile(r";\s*\w+"),  # semicolon followed by command
    re.compile(r"\|\|\s*\w+"),  # OR operator
    re.compile(r"&&\s*\w+"),  # AND operator
    re.compile(r"\|\s*\w+"),  # pipe to command
    re.compile(r"`[^`]+`"),  # backtick command substitution
    re.compile(r"\$\([^)]+\)"),  # $() command substitution
    re.compile(r"\$\{[^}]+\}"),  # ${} variable expansion
    re.compile(r">\s*/\w+"),  # redirect to system file
    re.compile(r"<\s*/\w+"),  # redirect from system file
]

# ANSI escape pattern (pre-compiled)
_ANSI_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Prompt injection patterns (pre-compiled)
_PROMPT_INJECTION_PATTERNS = re.compile(
    r"ignore previous (?:instructions?|commands?)|"
    r"ignore all (?:instructions?|guidelines?)|"
    r"you are now (?:a|an)|"
    r"disregard (?:all|previous)|"
    r"change your system prompt|"
    r"reveal your system prompt|"
    r"system prompt|"
    r"break character",
    re.IGNORECASE,
)

# ═══════════════════════════════════════════════════════════════════════
# Rust JSON serialization (try to import for better performance)
# Falls back to Python if Rust extension not available
# ═══════════════════════════════════════════════════════════════════════

try:
    from aidd_intern_core import (
        json_dumps_sorted as _json_dumps_rust,
        check_path_traversal as _check_path_traversal_rust,
        check_command_injection as _check_command_injection_rust,
        check_ansi_escapes as _check_ansi_escapes_rust,
        check_prompt_injection as _check_prompt_injection_rust,
    )
except ImportError:
    _check_path_traversal_rust = None
    _check_command_injection_rust = None
    _check_ansi_escapes_rust = None
    _check_prompt_injection_rust = None

    # Fallback to Python implementation
    def _json_dumps_rust(args: dict[str, Any]) -> str:
        """Fallback Python JSON serialization."""
        return _json.dumps(args, default=str)


# ── MCP Safety Constants ──────────────────────────────────────────────────
_MCP_TOOL_DESCRIPTION_MAX_LEN = 2000
_MCP_SUSPICIOUS_PATTERNS = [
    "ignore previous",
    "ignore all instructions",
    "system prompt",
    "you are now",
    "disregard",
]
_MCP_REQUIRES_APPROVAL: set[str] = set()  # Hook for future configuration

# ── Parameter Validation Helpers ───────────────────────────────────────────
_MAX_ARGS_SIZE_BYTES = 102400  # 100 KB


def _check_args_size(args: dict[str, Any]) -> Optional[str]:
    """Return an error string if serialized args exceed 100 KB, else None."""
    try:
        # Use Rust version for better performance
        serialized = _json_dumps_rust(args)
    except (TypeError, ValueError):
        return None
    if len(serialized.encode("utf-8")) > _MAX_ARGS_SIZE_BYTES:
        return (
            f"Tool arguments too large ({len(serialized.encode('utf-8'))} bytes, "
            f"max {_MAX_ARGS_SIZE_BYTES}). Reduce argument size."
        )
    return None


def _check_path_traversal(args: dict[str, Any]) -> Optional[str]:
    """Recursively check string values for path traversal patterns.

    Returns an error string if dangerous patterns are found, blocking execution.
    Blocks execution to prevent unauthorized file access.
    """
    if _check_path_traversal_rust is not None:
        try:
            return _check_path_traversal_rust(args)
        except Exception as e:
            logger.warning(
                f"Rust check_path_traversal failed, falling back to Python: {e}"
            )

    suspicious_paths: list[str] = []
    dangerous_patterns = ["../", "..\\\\", "..\\", "file://", "data://", "phar://"]

    def _scan(value: Any, key_path: str = "") -> None:
        if isinstance(value, str):
            for pattern in dangerous_patterns:
                if pattern in value:
                    suspicious_paths.append(
                        f"{key_path or '<value>'} (pattern: {pattern})"
                    )
                    break  # Only report once per value
        elif isinstance(value, dict):
            for key, val in value.items():
                _scan(val, f"{key_path}.{key}" if key_path else key)
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                _scan(item, f"{key_path}[{idx}]")

    _scan(args)
    if suspicious_paths:
        return (
            f"❌ Path traversal detected in: {', '.join(suspicious_paths)}. "
            f"Execution blocked for security. If this is a false positive, "
            f"contact the system administrator."
        )
    return None


def _check_command_injection(args: dict[str, Any]) -> Optional[str]:
    """Recursively check for command injection patterns.

    Blocks execution to prevent shell/command injection attacks.
    Detects common injection vectors and dangerous command patterns.
    """
    if _check_command_injection_rust is not None:
        try:
            return _check_command_injection_rust(args)
        except Exception as e:
            logger.warning(
                f"Rust check_command_injection failed, falling back to Python: {e}"
            )

    suspicious_entries: list[str] = []

    # Dangerous command keywords
    dangerous_commands = [
        "rm -rf",
        "format",
        "del",
        "rd",
        "mkdir",
        "rmdir",
        "wget",
        "curl",
        "nc",
        "netcat",
        "ssh",
        "scp",
        "rsync",
        "python -c",
        "python3 -c",
        "perl -e",
        "ruby -e",
        "lua -e",
        "eval",
        "exec",
        "source",
        ".",
        "bash -c",
        "sh -c",
        "chmod",
        "chown",
        "passwd",
        "sudo",
        "su -",
        "mkfifo",
        "mknod",
        ">>",
        ">",
    ]

    def _scan(value: Any, key_path: str = "") -> None:
        if isinstance(value, str):
            # Check for injection patterns (pre-compiled, cached)
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(value):
                    suspicious_entries.append(
                        f"{key_path or '<value>'} (pattern: {pattern.pattern})"
                    )
                    break

            # Check for dangerous commands
            value_lower = value.lower()
            for cmd in dangerous_commands:
                if cmd in value_lower:
                    suspicious_entries.append(
                        f"{key_path or '<value>'} (dangerous command: {cmd})"
                    )
                    break

        elif isinstance(value, dict):
            for key, val in value.items():
                _scan(val, f"{key_path}.{key}" if key_path else key)

        elif isinstance(value, list):
            for idx, item in enumerate(value):
                _scan(item, f"{key_path}[{idx}]")

    _scan(args)

    if suspicious_entries:
        return (
            f"⚠️  Command injection detected in: {', '.join(suspicious_entries)}. "
            f"Execution blocked for security. If this is a false positive, "
            f"contact the system administrator."
        )
    return None


def _check_ansi_escapes(args: dict[str, Any]) -> Optional[str]:
    """Check for ANSI escape sequences which could be used for prompt injection.

    Detects and warns about ANSI codes that might be used maliciously.
    """
    if _check_ansi_escapes_rust is not None:
        try:
            return _check_ansi_escapes_rust(args)
        except Exception as e:
            logger.warning(
                f"Rust check_ansi_escapes failed, falling back to Python: {e}"
            )

    suspicious_entries: list[str] = []

    def _scan(value: Any, key_path: str = "") -> None:
        if isinstance(value, str):
            # Use pre-compiled pattern (cached at module level)
            if _ANSI_PATTERN.search(value):
                suspicious_entries.append(f"{key_path or '<value>'}")

        elif isinstance(value, dict):
            for key, val in value.items():
                _scan(val, f"{key_path}.{key}" if key_path else key)

        elif isinstance(value, list):
            for idx, item in enumerate(value):
                _scan(item, f"{key_path}[{idx}]")

    _scan(args)

    if suspicious_entries:
        return (
            f"⚠️  ANSI escape sequences detected in: {', '.join(suspicious_entries)}. "
            f"These may be used for prompt injection. Review the input carefully."
        )
    return None


def _check_prompt_injection(args: dict[str, Any]) -> Optional[str]:
    """Check for prompt injection patterns in tool arguments.

    Detects attempts to modify system behavior or bypass security.
    """
    if _check_prompt_injection_rust is not None:
        try:
            return _check_prompt_injection_rust(args)
        except Exception as e:
            logger.warning(
                f"Rust check_prompt_injection failed, falling back to Python: {e}"
            )

    suspicious_entries: list[str] = []

    def _scan(value: Any, key_path: str = "") -> None:
        if isinstance(value, str):
            # Use pre-compiled pattern (cached at module level)
            if _PROMPT_INJECTION_PATTERNS.search(value):
                suspicious_entries.append(f"{key_path or '<value>'}")

        elif isinstance(value, dict):
            for key, val in value.items():
                _scan(val, f"{key_path}.{key}" if key_path else key)

        elif isinstance(value, list):
            for idx, item in enumerate(value):
                _scan(item, f"{key_path}[{idx}]")

    _scan(args)

    if suspicious_entries:
        return (
            f"⚠️  Prompt injection pattern detected in: {', '.join(suspicious_entries)}. "
            f"This may be a security attempt. Block execution."
        )
    return None


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
    {
        "name": "run_rfd3",
        "description": (
            "Generate protein binders with atom-level precision and all-atom modeling using RFdiffusion3 (RFD3). "
            "Optimized for 10x speedup and high-precision target hotspot compliance."
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
                "hotspot_residues": {
                    "type": "string",
                    "description": "Optional comma-separated target hotspot residue numbers.",
                },
                "atom_precision": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to request all-atom high-precision modeling.",
                },
                "tool_runtime": {
                    "type": "string",
                    "enum": ["local", "sandbox"],
                    "default": "local",
                },
            },
            "required": ["target_pdb"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_rfd3_tool",
    },
    {
        "name": "run_chai1",
        "description": (
            "Evaluate a protein-binder complex structure using Chai-1. "
            "Calculates orthogonal validation metrics: ipTM, pLDDT, and pAE."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "complex_pdb": {
                    "type": "string",
                    "description": "Path to the complex PDB file to evaluate.",
                }
            },
            "required": ["complex_pdb"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_chai1_tool",
    },
    {
        "name": "run_protenix",
        "description": (
            "Evaluate a protein-binder complex structure using Protenix as an "
            "orthogonal validation model. Calculates ipTM, pLDDT, and pAE."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "complex_pdb": {
                    "type": "string",
                    "description": "Path to the complex PDB file to evaluate.",
                }
            },
            "required": ["complex_pdb"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_protenix_tool",
    },
    {
        "name": "run_proteinmpnn",
        "description": (
            "Design amino acid sequences for a given protein backbone using ProteinMPNN. "
            "Useful for sequence optimization of designed binders."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "backbone_pdb": {
                    "type": "string",
                    "description": "Path to backbone PDB file.",
                },
                "num_sequences": {
                    "type": "integer",
                    "default": 10,
                    "description": "Number of sequences to generate per backbone.",
                },
                "temperature": {
                    "type": "number",
                    "default": 0.1,
                    "description": "Sampling temperature (lower = more conservative).",
                },
                "chain_id": {
                    "type": "string",
                    "default": "A",
                    "description": "Chain ID to design.",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for designed sequences.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Command timeout in seconds.",
                },
            },
            "required": ["backbone_pdb"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_proteinmpnn_tool",
    },
    {
        "name": "run_esmfold",
        "description": (
            "Predict 3D structure from amino acid sequence using ESMFold. "
            "Fast single-sequence structure prediction without MSA."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sequence": {
                    "type": "string",
                    "description": "Amino acid sequence (single-letter code).",
                },
                "output_pdb": {
                    "type": "string",
                    "description": "Output PDB file path.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Command timeout in seconds.",
                },
            },
            "required": ["sequence"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_esmfold_tool",
    },
    {
        "name": "run_foldseek",
        "description": (
            "Cluster or search protein structures using Foldseek. "
            "Modes: 'cluster' for structure clustering, 'search' for structure search, "
            "'createdb' for creating a Foldseek database."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "description": "Path to input PDB file(s) or directory.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["cluster", "search", "createdb"],
                    "default": "cluster",
                    "description": "Foldseek operation mode.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Output path for results.",
                },
                "min_seq_id": {
                    "type": "number",
                    "default": 0.3,
                    "description": "Minimum sequence identity for clustering.",
                },
                "db_path": {
                    "type": "string",
                    "description": "Database path (required for search mode).",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Command timeout in seconds.",
                },
            },
            "required": ["input_path"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_foldseek_tool",
    },
    {
        "name": "run_sequence_analysis",
        "description": (
            "Analyse protein sequence properties including hydrophobicity (GRAVY), "
            "net charge at pH 7, aggregation propensity, and ESM2 pseudo-log-likelihood (PLL). "
            "Use for quality assessment of designed sequences."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sequence": {
                    "type": "string",
                    "description": "Amino acid sequence (single-letter code).",
                },
                "analyses": {
                    "type": "string",
                    "description": (
                        "Comma-separated list of analyses to run. "
                        "Options: hydrophobicity, charge, aggregation, esm2_pll. "
                        "Default: all."
                    ),
                },
            },
            "required": ["sequence"],
        },
        "module": "agent.workflows.protein_design.tools",
        "handler": "_sequence_analysis_tool",
    },
]


_MEMU_TOOL_SPECS = [
    {
        "name": "memu_retrieve_memories",
        "description": (
            "Retrieve persistent user preferences, past binder-design campaign histories, "
            "hyperparameter recommendations, and successful tool-orchestration strategies using MemU semantic search. "
            "USE THIS TOOL to 'remember' what worked in previous runs or query user's specific instructions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Semantic query describing what memory, preference, or past run parameters to search.",
                },
                "user_id": {
                    "type": "string",
                    "default": "default_user",
                    "description": "Unique identifier of the user to fetch memories for.",
                },
                "agent_id": {
                    "type": "string",
                    "default": "default_agent",
                    "description": "Unique identifier of the agent.",
                },
            },
            "required": ["query"],
        },
        "handler": "memu_retrieve_handler",
    },
    {
        "name": "memu_memorize_session",
        "description": (
            "Memorize the current conversation context, successful binder design hyperparams, "
            "or new custom protocols to MemU persistent memory layer. Extracts structured memory categories for future use."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "conversation": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["user", "assistant"]},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                    },
                    "description": "List of recent conversation messages (minimum 3 messages) to extract memory from.",
                },
                "user_id": {
                    "type": "string",
                    "default": "default_user",
                    "description": "Unique identifier of the user.",
                },
                "agent_id": {
                    "type": "string",
                    "default": "default_agent",
                    "description": "Unique identifier of the agent.",
                },
                "user_name": {
                    "type": "string",
                    "description": "Display name of the user.",
                },
                "agent_name": {
                    "type": "string",
                    "description": "Display name of the agent.",
                },
            },
            "required": ["conversation"],
        },
        "handler": "memu_memorize_handler",
    },
    {
        "name": "update_task_canvas",
        "description": (
            "Update the Symbolic Short-Term Memory task canvas. This canvas allows tracking complex workflow steps, "
            "adding task execution states, detailing run durations, and visually chaining tasks via DAG edges."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Name or identifier of the workflow step/node to add or update.",
                },
                "status": {
                    "type": "string",
                    "enum": ["PENDING", "RUNNING", "SUCCESS", "FAILED"],
                    "default": "PENDING",
                    "description": "Status state of the workflow step/node.",
                },
                "details": {
                    "type": "string",
                    "description": "Optional human-readable execution details or performance duration (e.g. '0.45s', 'processing structural alignment').",
                },
                "edge_to": {
                    "type": "string",
                    "description": "Optional target node name to draw a directed DAG edge from this node to the target node.",
                },
            },
            "required": ["node"],
        },
        "handler": "update_task_canvas_handler",
    },
]


async def memu_retrieve_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    from agent.core.memu import MemUClient
    from agent.core.memory import LayeredMemoryPipeline

    client = MemUClient()
    if not client.is_configured():
        return (
            "Error: MEMU_API_KEY environment variable is not configured. MemU long-term memory is disabled.",
            False,
        )
    query = arguments["query"]
    user_id = arguments.get("user_id") or "default_user"
    agent_id = arguments.get("agent_id") or "default_agent"
    try:
        pipeline = LayeredMemoryPipeline(client=client)
        user_name = "User"
        if session and getattr(session, "hf_username", None):
            user_name = session.hf_username

        res = await pipeline.aretrieve_layered(
            user_id=user_id, agent_id=agent_id, query=query, user_name=user_name
        )
        import json

        return json.dumps(res, indent=2, ensure_ascii=False), True
    except Exception as e:
        return f"Error retrieving memories: {e}", False


async def update_task_canvas_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    if (
        session is None
        or not hasattr(session, "task_canvas")
        or session.task_canvas is None
    ):
        return (
            "Error: Session task canvas is uninitialized or unavailable in the current context.",
            False,
        )

    node = arguments["node"]
    status = arguments.get("status") or "PENDING"
    details = arguments.get("details")
    edge_to = arguments.get("edge_to")

    session.task_canvas.update_node(node, status, details)
    if edge_to:
        session.task_canvas.add_edge(node, edge_to)

    rendered = session.task_canvas.render_mermaid()
    return (
        f"Successfully updated task canvas node '{node}' to state '{status}'.\n\nCurrent Canvas:\n{rendered}",
        True,
    )


_KNOWLEDGE_WIKI_TOOL_SPECS = [
    {
        "name": "knowledge_wiki_search",
        "description": (
            "Search the Binder Design Knowledge Wiki for historical experience, "
            "successful strategies, hyperparameter recommendations, and lessons "
            "learned from past design campaigns. Use this to leverage accumulated "
            "experience when planning new binder design workflows."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query describing what experience or strategy to find. "
                        "Examples: 'PD-L1 binder design', 'BindCraft optimization', 'high ipTM strategies'."
                    ),
                },
                "target": {
                    "type": "string",
                    "description": "Optional target protein name to filter results.",
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "target",
                        "tool_chain",
                        "strategy",
                        "failure_mode",
                        "benchmark",
                    ],
                    "description": "Optional category filter.",
                },
                "top_k": {
                    "type": "integer",
                    "default": 3,
                    "description": "Maximum number of results to return.",
                },
            },
            "required": ["query"],
        },
        "handler": "knowledge_wiki_search_handler",
    },
]


async def knowledge_wiki_search_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    """Tool handler: search the knowledge wiki and return formatted results."""
    from agent.core.knowledge_wiki import KnowledgeWiki

    query = arguments["query"]
    target = arguments.get("target")
    category_filter = arguments.get("category")
    top_k = arguments.get("top_k", 3)

    try:
        wiki = KnowledgeWiki()
        if wiki.entry_count == 0:
            return (
                "Knowledge Wiki is empty. No historical experience recorded yet. "
                "Complete a successful binder design session to start accumulating knowledge.",
                True,
            )

        prompt = wiki.get_context_prompt(
            query, target=target, top_k=top_k, category=category_filter
        )
        if not prompt:
            return f"No matching entries found for query: '{query}'", True
        return prompt, True
    except Exception as e:
        return f"Error searching knowledge wiki: {e}", False


async def memu_memorize_handler(arguments: dict[str, Any]) -> tuple[str, bool]:
    from agent.core.memu import MemUClient

    client = MemUClient()
    if not client.is_configured():
        return (
            "Error: MEMU_API_KEY environment variable is not configured. MemU long-term memory is disabled.",
            False,
        )
    conversation = arguments["conversation"]
    user_id = arguments.get("user_id") or "default_user"
    agent_id = arguments.get("agent_id") or "default_agent"
    user_name = arguments.get("user_name")
    agent_name = arguments.get("agent_name")
    try:
        res = await client.amemorize(
            conversation=conversation,
            user_id=user_id,
            agent_id=agent_id,
            user_name=user_name,
            agent_name=agent_name,
        )
        import json

        return json.dumps(res, indent=2, ensure_ascii=False), res.get(
            "status"
        ) != "FAILED"
    except Exception as e:
        return f"Error saving session memory: {e}", False


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

    _tool_timeout_seconds: float = 30.0  # Default tool execution timeout

    def __init__(
        self,
        mcp_servers: dict[str, MCPServerConfig],
        hf_token: str | None = None,
        local_mode: bool = False,
        tool_timeout_seconds: float = 30.0,
    ):
        """
        Initialize ToolRouter.

        Args:
            mcp_servers: MCP server configurations
            hf_token: Hugging Face token for authentication
            local_mode: Whether to use local filesystem tools
            tool_timeout_seconds: Default timeout for tool execution (default: 30s)
        """
        self.tools: dict[str, ToolSpec] = {}
        self.mcp_servers: dict[str, dict[str, Any]] = {}
        self._tool_timeout_seconds = tool_timeout_seconds

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

            description = tool.description or ""

            # Safety: truncate overly long descriptions
            if len(description) > _MCP_TOOL_DESCRIPTION_MAX_LEN:
                description = (
                    description[:_MCP_TOOL_DESCRIPTION_MAX_LEN]
                    + " [truncated for safety]"
                )

            # Safety: detect prompt-injection patterns in description
            description_lower = description.lower()
            has_suspicious = any(
                pat in description_lower for pat in _MCP_SUSPICIOUS_PATTERNS
            )
            if has_suspicious:
                logger.warning(
                    "MCP tool '%s' has suspicious patterns in description", tool.name
                )

            metadata: dict[str, Any] = {}
            if has_suspicious:
                metadata["safety_note"] = (
                    "[SAFETY: description contained suspicious patterns]"
                )

            registered_names.append(tool.name)
            self.register_tool(
                ToolSpec(
                    name=tool.name,
                    description=description,
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
        timeout_seconds: float | None = None,
    ) -> tuple[str, bool]:
        """
        Call a tool and return (output_string, success_bool).

        For MCP tools, converts the CallToolResult content blocks to a string.
        For built-in tools, calls their handler directly.

        Implements comprehensive security checks according to AHE:
        - Execution layer: argument validation, command injection blocking
        - Tooling layer: parameter size limits, schema validation
        - Validation layer: ANSI escape detection, prompt injection blocking

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments as a dictionary
            session: Optional session object for stateful tools
            tool_call_id: Optional tool call ID for MCP protocol
            timeout_seconds: Optional timeout override (default: instance default)

        Returns:
            Tuple of (output_string, success_bool)

        Raises:
            asyncio.TimeoutError: If tool execution exceeds timeout
        """
        # Use provided timeout or default
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self._tool_timeout_seconds
        )
        # Parameter size validation (Tooling layer)
        size_error = _check_args_size(arguments)
        if size_error:
            return size_error, False

        # Security checks (Execution and Validation layers)
        from agent.core.tools import (
            _check_path_traversal,
            _check_command_injection,
            _check_ansi_escapes,
            _check_prompt_injection,
        )

        # Path traversal - BLOCK (Execution layer)
        path_error = _check_path_traversal(arguments)
        if path_error:
            return path_error, False

        # Command injection - BLOCK (Execution layer)
        cmd_error = _check_command_injection(arguments)
        if cmd_error:
            return cmd_error, False

        # ANSI escapes - WARN (Validation layer)
        ansi_warning = _check_ansi_escapes(arguments)

        # Prompt injection - BLOCK (Validation layer)
        prompt_error = _check_prompt_injection(arguments)
        if prompt_error:
            return prompt_error, False

        # Check if this is a built-in tool with a handler
        tool = self.tools.get(tool_name)
        if tool and tool.handler:
            # Wrap tool execution with timeout
            try:
                async with asyncio.timeout(timeout):
                    # Check if handler accepts session argument
                    params = getattr(tool.handler, "_tool_param_names", None)
                    accepts_kwargs = getattr(
                        tool.handler, "_tool_accepts_kwargs", False
                    )
                    if params is None:
                        import inspect

                        params = set(inspect.signature(tool.handler).parameters)
                    if "session" in params or accepts_kwargs:
                        # Check if handler also accepts tool_call_id parameter
                        if "tool_call_id" in params or accepts_kwargs:
                            output, ok = await tool.handler(
                                arguments, session=session, tool_call_id=tool_call_id
                            )
                        else:
                            output, ok = await tool.handler(arguments, session=session)
                    else:
                        output, ok = await tool.handler(arguments)
                    # Append ANSI warning if present
                    if ansi_warning:
                        output = ansi_warning + "\n" + output
                    return output, ok
            except asyncio.TimeoutError:
                return (
                    f"❌ Tool execution timeout after {timeout}s. "
                    f"Consider increasing the timeout or optimizing the tool."
                ), False

        # Otherwise, use MCP client
        if self._mcp_initialized:
            try:
                # Wrap MCP tool call with timeout
                async with asyncio.timeout(timeout):
                    result = await self.mcp_client.call_tool(tool_name, arguments)
                    output = convert_mcp_content_to_string(result.content)
                    # Append ANSI warning if present
                    if ansi_warning:
                        output = ansi_warning + "\n" + output
                    return output, not result.is_error
            except asyncio.TimeoutError:
                return (
                    f"❌ MCP tool execution timeout after {timeout}s. "
                    f"Consider increasing the timeout or using a faster tool."
                ), False
            except ToolError as e:
                # Catch MCP tool errors and return them to the agent
                error_msg = f"Tool error: {str(e)}"
                return error_msg, False
        else:
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
            "agent.tools.aidd_prepare_tool",
            "AIDD_PREPARE_TOOL_SPEC",
            "aidd_prepare_handler",
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

    tools.extend(
        ToolSpec(
            name=spec["name"],
            description=spec["description"],
            parameters=spec["parameters"],
            handler=globals()[spec["handler"]],
        )
        for spec in _MEMU_TOOL_SPECS
    )

    tools.extend(
        ToolSpec(
            name=spec["name"],
            description=spec["description"],
            parameters=spec["parameters"],
            handler=globals()[spec["handler"]],
        )
        for spec in _KNOWLEDGE_WIKI_TOOL_SPECS
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
