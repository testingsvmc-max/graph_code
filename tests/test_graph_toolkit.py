"""Tests for clangd-graph-rag export graph toolkit (MCP-style tool dispatch, YAML GraphStore)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code_graph_api.graph_toolkit import invoke_tool, list_tools_catalog
from code_graph_api.store import GraphStore


def _minimal_graph() -> GraphStore:
    graph = {
        "meta": {},
        "nodes": [
            {"id": "file:a.c", "labels": ["FILE"], "properties": {"path": "a.c"}},
            {"id": "F1", "labels": ["FUNCTION"], "properties": {"name": "f1", "file_path": "a.c", "line_start": 1, "line_end": 200}},
            {"id": "F2", "labels": ["FUNCTION"], "properties": {"name": "f2", "file_path": "a.c"}},
        ],
        "edges": [
            {"type": "DEFINES", "src": "file:a.c", "dst": "F1", "properties": {}},
            {"type": "DEFINES", "src": "file:a.c", "dst": "F2", "properties": {}},
            {"type": "CALLS", "src": "F1", "dst": "F2", "properties": {}},
        ],
    }
    return GraphStore(graph)


def test_list_graph_stats_tool() -> None:
    s = _minimal_graph()
    r = invoke_tool(s, "list_graph_stats_tool", {})
    assert r["status"] == "ok"
    assert r["stats"]["nodes"] == 3


def test_query_and_traverse() -> None:
    s = _minimal_graph()
    r = invoke_tool(s, "query_graph_tool", {"pattern": "callees_of", "target": "F1"})
    assert r["status"] == "ok"
    assert r["result_count"] >= 1
    tr = invoke_tool(s, "traverse_graph_tool", {"start": "F1", "edge_type": "CALLS", "depth": 1, "limit": 50})
    assert tr["status"] == "ok"


def test_unsupported_tool_shape() -> None:
    s = _minimal_graph()
    r = invoke_tool(s, "list_flows_tool", {})
    assert r["status"] == "unsupported"


def test_catalog_contains_implemented_and_stub() -> None:
    names = {t["name"]: t for t in list_tools_catalog()}
    assert names["list_graph_stats_tool"]["implemented"] is True
    assert names["list_flows_tool"]["implemented"] is False
