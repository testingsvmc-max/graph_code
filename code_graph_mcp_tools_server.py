#!/usr/bin/env python3
"""
FastMCP server: clangd-graph-rag export graph tools (YAML/JSON GraphStore, no Neo4j).

Dispatcher stays aligned with ``code_graph_api.graph_toolkit`` and ``POST /tools/invoke``
on the HTTP API.

Run:
  set GRAPH_PATH=D:\\path\\code_graph.yaml
  python code_graph_mcp_tools_server.py

Or:
  python code_graph_mcp_tools_server.py D:\\path\\code_graph.yaml
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastmcp import FastMCP

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code_graph_api.graph_toolkit import invoke_tool, list_tools_catalog
from code_graph_api.store import GraphStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("clangd-graph-rag-export-tools")
_store: Optional[GraphStore] = None


def _load_store() -> GraphStore:
    global _store
    if _store is not None:
        return _store
    path = os.environ.get("GRAPH_PATH")
    if not path:
        raise RuntimeError("Set GRAPH_PATH to a code_graph.yaml or .json export.")
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Graph file not found: {p}")
    _store = GraphStore.from_path(str(p))
    logger.info("Loaded graph: %s (%s nodes)", p, len(_store.nodes))
    return _store


@mcp.tool(
    name="invoke_graph_tool",
    description=(
        "Invoke a clangd-graph-rag export graph tool on the loaded YAML/JSON. "
        "tool_name must match catalog from list_graph_tools (e.g. list_graph_stats_tool, query_graph_tool). "
        "arguments_json is a JSON object string, e.g. '{}' or '{\"pattern\":\"callers_of\",\"target\":\"<id>\"}'."
    ),
)
def invoke_graph_tool(tool_name: str, arguments_json: str = "{}") -> Dict[str, Any]:
    try:
        args = json.loads(arguments_json) if arguments_json.strip() else {}
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"Invalid arguments_json: {e}"}
    if not isinstance(args, dict):
        return {"status": "error", "error": "arguments_json must decode to an object"}
    store = _load_store()
    return invoke_tool(store, tool_name, args)


@mcp.tool(
    name="list_graph_tools",
    description="List export graph tool names and whether they are implemented on YAML/JSON exports.",
)
def list_graph_tools() -> Dict[str, Any]:
    _load_store()
    return {"tools": list_tools_catalog()}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        os.environ["GRAPH_PATH"] = str(Path(sys.argv[1]).expanduser().resolve())
    _load_store()
    mcp.run(transport="streamable-http", host=os.environ.get("MCP_HOST", "127.0.0.1"), port=int(os.environ.get("MCP_PORT", "8810")))
