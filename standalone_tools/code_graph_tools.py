#!/usr/bin/env python3
"""
CLI for clangd-graph-rag export graph tools (same surface as ``POST /tools/invoke``).

Examples:
  python standalone_tools/code_graph_tools.py graph.yaml catalog
  python standalone_tools/code_graph_tools.py graph.yaml invoke list_graph_stats_tool
  python standalone_tools/code_graph_tools.py graph.yaml invoke query_graph_tool --args '{"pattern":"callers_of","target":"<node_id>"}'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code_graph_api.graph_toolkit import invoke_tool, list_tools_catalog
from code_graph_api.store import GraphStore


def main() -> int:
    p = argparse.ArgumentParser(description="clangd-graph-rag export graph tools CLI (YAML/JSON)")
    p.add_argument("graph", type=Path, help="Path to code_graph.yaml or .json")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("catalog", help="Print tool catalog JSON")

    p_inv = sub.add_parser("invoke", help="Run one tool")
    p_inv.add_argument("tool", type=str, help="Tool name, e.g. list_graph_stats_tool")
    p_inv.add_argument(
        "--args",
        type=str,
        default="{}",
        help="JSON object of arguments (default: {})",
    )

    args = p.parse_args()
    g = args.graph.expanduser().resolve()
    if not g.is_file():
        print(f"Not found: {g}", file=sys.stderr)
        return 2
    store = GraphStore.from_path(str(g))

    if args.cmd == "catalog":
        print(json.dumps({"tools": list_tools_catalog()}, indent=2, ensure_ascii=False))
        return 0

    try:
        arguments = json.loads(args.args)
    except json.JSONDecodeError as e:
        print(f"Invalid --args JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(arguments, dict):
        print("--args must be a JSON object", file=sys.stderr)
        return 2

    out = invoke_tool(store, args.tool, arguments)
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if (isinstance(out, dict) and out.get("status") != "error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
