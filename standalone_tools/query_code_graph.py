#!/usr/bin/env python3
"""
CLI query tools for exported code_graph.yaml/json (no MCP, no Neo4j).
Similar intent to common MCP-style graph query tools.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code_graph_api.store import GraphStore


def _print(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> int:
    p = argparse.ArgumentParser(description="Query exported graph YAML/JSON locally")
    p.add_argument("graph_file", type=Path, help="Path to code_graph.yaml/json")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats", help="List graph stats")

    s = sub.add_parser("search", help="Search nodes/functions")
    s.add_argument("query", type=str)
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--all-nodes", action="store_true", help="Search all nodes instead of function-focused search")

    q = sub.add_parser("query", help="Run predefined pattern query")
    q.add_argument("pattern", type=str, help="callers_of|callees_of|imports_of|importers_of|children_of|tests_for|inheritors_of|file_summary")
    q.add_argument("target", type=str)
    q.add_argument("--limit", type=int, default=200)

    t = sub.add_parser("traverse", help="Traverse graph from start node")
    t.add_argument("start", type=str)
    t.add_argument("--direction", choices=["up", "down", "both"], default="both")
    t.add_argument("--edge-type", default="CALLS")
    t.add_argument("--depth", type=int, default=2)
    t.add_argument("--limit", type=int, default=500)

    ir = sub.add_parser("impact-radius", help="Estimate blast radius from changed files")
    ir.add_argument("changed_files", nargs="+", help="Changed file paths")
    ir.add_argument("--max-depth", type=int, default=2)
    ir.add_argument("--limit", type=int, default=500)

    args = p.parse_args()
    try:
        store = GraphStore.from_path(str(args.graph_file.resolve()))
    except Exception as exc:
        print(f"Failed to load graph file: {args.graph_file} ({exc})", file=sys.stderr)
        return 2

    if args.cmd == "stats":
        _print(store.list_graph_stats())
        return 0
    if args.cmd == "search":
        res = store.search_nodes(args.query, args.limit) if args.all_nodes else store.search_functions(args.query, args.limit)
        _print({"query": args.query, "count": len(res), "results": res})
        return 0
    if args.cmd == "query":
        _print(store.query_graph(pattern=args.pattern, target=args.target, limit=args.limit))
        return 0
    if args.cmd == "traverse":
        _print(store.traverse_graph(start=args.start, direction=args.direction, edge_type=args.edge_type, depth=args.depth, limit=args.limit))
        return 0
    if args.cmd == "impact-radius":
        _print(store.impact_radius(changed_files=args.changed_files, max_depth=args.max_depth, limit=args.limit))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
