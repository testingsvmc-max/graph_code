"""
ADK agent over exported code_graph.yaml/json only: direct Python tools (no MCP, no Neo4j).

Set ``CODE_GRAPH_YAML`` or ``GRAPH_PATH`` to the export file before loading ``root_agent``
(e.g. ``<project>/.clangd-graph-rag/code_graph.yaml``). Tools call ``graph_toolkit.invoke_tool``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from pprint import pprint
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from code_graph_api.graph_toolkit import invoke_tool, list_tools_catalog
from code_graph_api.store import GraphStore

_STORE: GraphStore | None = None
_MAX_TOOL_JSON_CHARS = 120_000


def _graph_path() -> Path:
    raw = os.environ.get("CODE_GRAPH_YAML") or os.environ.get("GRAPH_PATH") or ""
    if not raw.strip():
        raise RuntimeError(
            "Set CODE_GRAPH_YAML or GRAPH_PATH to your code_graph.yaml or .json export "
            "(e.g. project/.clangd-graph-rag/code_graph.yaml)."
        )
    p = Path(raw).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Graph export not found: {p}")
    return p


def _get_store() -> GraphStore:
    global _STORE
    if _STORE is None:
        _STORE = GraphStore.from_path(str(_graph_path()))
    return _STORE


def _json_response(payload: Any) -> str:
    s = json.dumps(payload, ensure_ascii=False, default=str)
    if len(s) <= _MAX_TOOL_JSON_CHARS:
        return s
    return s[: _MAX_TOOL_JSON_CHARS - 120] + "\n... [truncated; narrow the tool args or use a smaller depth/limit]"


def list_export_graph_tools() -> str:
    """List all MCP-style graph tool names for this YAML/JSON export (implemented + unsupported stubs).

    Returns:
        JSON array of objects with keys: name, implemented, and either description or reason.
    """
    try:
        _ = _get_store()
    except Exception as exc:
        return _json_response({"status": "error", "error": str(exc)})
    return _json_response(list_tools_catalog())


def invoke_export_graph_tool(tool_name: str, arguments_json: str = "{}") -> str:
    """Run one export graph tool by name; arguments are a JSON object string.

    Args:
        tool_name: e.g. list_graph_stats_tool, query_graph_tool, traverse_graph_tool, get_impact_radius_tool.
        arguments_json: JSON object, e.g. '{}' or '{"pattern":"callers_of","target":"src/a.c::foo"}'.

    Returns:
        JSON string: tool result (status ok/error/unsupported/not_found, etc.).
    """
    try:
        store = _get_store()
    except Exception as exc:
        return _json_response({"status": "error", "error": str(exc)})
    try:
        args = json.loads(arguments_json or "{}")
        if not isinstance(args, dict):
            return _json_response({"status": "error", "error": "arguments_json must be a JSON object"})
    except json.JSONDecodeError as exc:
        return _json_response({"status": "error", "error": f"Invalid JSON: {exc}"})
    out = invoke_tool(store, tool_name, args)
    return _json_response(out)


def export_graph_guardrail(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    agent_name = callback_context.agent_name
    if llm_request.contents:
        content = llm_request.contents[-1]
        if content.role == "user" and content.parts and content.parts[0].text:
            if "shit" in content.parts[0].text.lower():
                print(f"{agent_name} Guardrail triggered. Conversation so far:")
                for c in llm_request.contents:
                    pprint(c)
                return LlmResponse(
                    content=types.Content(
                        role="assistant",
                        parts=[types.Part(text="I'm sorry, but I can't assist with that.")],
                    )
                )
    return None


def _instruction() -> str:
    p = os.environ.get("CODE_GRAPH_YAML") or os.environ.get("GRAPH_PATH") or "(set CODE_GRAPH_YAML)"
    return (
        "You are an expert software engineer helping analyze a C/C++ project using a **pre-exported code graph** "
        f"(YAML/JSON file: {p}). There is **no Neo4j** and **no Cypher** — only the tools provided.\n\n"
        "## Tools\n"
        "- Call `list_export_graph_tools` first to see which `*_tool` names exist and which are implemented.\n"
        "- Use `invoke_export_graph_tool` with `tool_name` and `arguments_json` (a JSON **string** of an object).\n\n"
        "## Common patterns (invoke_export_graph_tool)\n"
        "- Stats: tool_name=`list_graph_stats_tool`, arguments_json=`{}`\n"
        "- Callers: tool_name=`query_graph_tool`, arguments_json=`"
        '{"pattern":"callers_of","target":"<function_node_id>","limit":50}`\n'
        "- Callees: pattern `callees_of`.\n"
        "- Traverse CALLS: tool_name=`traverse_graph_tool`, "
        '`{"start":"<id>","direction":"both","edge_type":"CALLS","depth":2,"limit":200}`\n'
        "- Impact from changed files: tool_name=`get_impact_radius_tool`, "
        '`{"changed_files":["src/a.c","include/h.h"],"max_depth":2,"limit":500}`\n'
        "- Lexical search on nodes: tool_name=`semantic_search_nodes_tool`, "
        '`{"query":"keyword","limit":30}` (lexical; true vectors are not in this export).\n\n'
        "## Node ids\n"
        "Targets are usually stable node ids from the export (e.g. qualified function id). "
        "If `query_graph_tool` returns `ambiguous`, disambiguate using search results.\n\n"
        "## Output\n"
        "Explain results in clear language; cite node ids and file paths from tool JSON when relevant."
    )


def build_export_graph_agent() -> LlmAgent:
    model_name = os.environ.get("LLM_MODEL", "deepseek/deepseek-chat")
    llm = LiteLlm(model=model_name)
    return LlmAgent(
        model=llm,
        name="Export_Graph_Agent",
        instruction=_instruction(),
        tools=[list_export_graph_tools, invoke_export_graph_tool],
        output_key="last_response",
        before_model_callback=export_graph_guardrail,
    )


root_agent = build_export_graph_agent()
