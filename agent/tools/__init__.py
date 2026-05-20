"""AIDD-Intern tools for the agent.

Keep this package initializer lightweight. Several tool modules import large
optional dependencies; load them only when the specific tool is requested.
"""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "ToolResult": ("agent.tools.types", "ToolResult"),
    "AIDD_BIO_TOOL_SPEC": ("agent.tools.aidd_bio_tool", "AIDD_BIO_TOOL_SPEC"),
    "aidd_bio_handler": ("agent.tools.aidd_bio_tool", "aidd_bio_handler"),
    "BINDER_DESIGN_TOOL_SPEC": (
        "agent.tools.binder_design_tool",
        "BINDER_DESIGN_TOOL_SPEC",
    ),
    "binder_design_handler": (
        "agent.tools.binder_design_tool",
        "binder_design_handler",
    ),
    "HF_INSPECT_DATASET_TOOL_SPEC": (
        "agent.tools.dataset_tools",
        "HF_INSPECT_DATASET_TOOL_SPEC",
    ),
    "hf_inspect_dataset_handler": (
        "agent.tools.dataset_tools",
        "hf_inspect_dataset_handler",
    ),
    "GITHUB_FIND_EXAMPLES_TOOL_SPEC": (
        "agent.tools.github_find_examples",
        "GITHUB_FIND_EXAMPLES_TOOL_SPEC",
    ),
    "github_find_examples_handler": (
        "agent.tools.github_find_examples",
        "github_find_examples_handler",
    ),
    "GITHUB_LIST_REPOS_TOOL_SPEC": (
        "agent.tools.github_list_repos",
        "GITHUB_LIST_REPOS_TOOL_SPEC",
    ),
    "github_list_repos_handler": (
        "agent.tools.github_list_repos",
        "github_list_repos_handler",
    ),
    "GITHUB_READ_FILE_TOOL_SPEC": (
        "agent.tools.github_read_file",
        "GITHUB_READ_FILE_TOOL_SPEC",
    ),
    "github_read_file_handler": (
        "agent.tools.github_read_file",
        "github_read_file_handler",
    ),
    "HF_JOBS_TOOL_SPEC": ("agent.tools.jobs_tool", "HF_JOBS_TOOL_SPEC"),
    "HfJobsTool": ("agent.tools.jobs_tool", "HfJobsTool"),
    "hf_jobs_handler": ("agent.tools.jobs_tool", "hf_jobs_handler"),
    "WEB_SEARCH_TOOL_SPEC": ("agent.tools.web_search_tool", "WEB_SEARCH_TOOL_SPEC"),
    "web_search_handler": ("agent.tools.web_search_tool", "web_search_handler"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
