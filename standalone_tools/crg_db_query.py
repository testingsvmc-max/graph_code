#!/usr/bin/env python3
"""
Query clangd-graph-rag SQLite ``graph.db`` directly (no Neo4j).

Examples:
  python standalone_tools/crg_db_query.py --db path/to/graph.db search "wpa" --limit 20
  python standalone_tools/crg_db_query.py --db path/to/graph.db callers "src/a.c::foo"
  python standalone_tools/crg_db_query.py --db path/to/graph.db call-graph "src/a.c::foo" --direction both --depth 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from integrations.crg_sqlite import (
    call_graph_neighborhood,
    get_callees,
    get_callers,
    load_crg_db,
    resolve_function_target,
    search_nodes,
)


def _print(obj: object) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main() -> int:
    p = argparse.ArgumentParser(description="Query clangd-graph-rag graph.db (SQLite)")
    p.add_argument("--db", type=Path, required=True, help="Path to graph.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_search = sub.add_parser("search", help="Search function/method nodes")
    s_search.add_argument("query", type=str)
    s_search.add_argument("--limit", type=int, default=30)

    s_callers = sub.add_parser("callers", help="List callers of a function")
    s_callers.add_argument("target", type=str, help="qualified_name preferred")
    s_callers.add_argument("--resolve-limit", type=int, default=20)

    s_callees = sub.add_parser("callees", help="List callees of a function")
    s_callees.add_argument("target", type=str, help="qualified_name preferred")
    s_callees.add_argument("--resolve-limit", type=int, default=20)

    s_graph = sub.add_parser("call-graph", help="CALLS neighborhood from a center function")
    s_graph.add_argument("target", type=str, help="qualified_name preferred")
    s_graph.add_argument("--direction", choices=["up", "down", "both"], default="both")
    s_graph.add_argument("--depth", type=int, default=1)
    s_graph.add_argument("--limit", type=int, default=500)
    s_graph.add_argument("--resolve-limit", type=int, default=20)

    args = p.parse_args()
    conn = load_crg_db(args.db.resolve())
    try:
        if args.cmd == "search":
            rows = search_nodes(conn, args.query, limit=args.limit)
            _print({"query": args.query, "count": len(rows), "results": rows})
            return 0

        resolved = resolve_function_target(conn, args.target, limit=args.resolve_limit)
        if resolved["status"] != "ok":
            _print(resolved)
            return 2
        node = resolved["node"]
        qn = node["qualified_name"]

        if args.cmd == "callers":
            rows = get_callers(conn, qn)
            _print({"target": node, "caller_count": len(rows), "callers": rows})
            return 0

        if args.cmd == "callees":
            rows = get_callees(conn, qn)
            _print({"target": node, "callee_count": len(rows), "callees": rows})
            return 0

        if args.cmd == "call-graph":
            out = call_graph_neighborhood(
                conn,
                qn,
                direction=args.direction,
                depth=args.depth,
                limit=args.limit,
            )
            out["center_node"] = node
            _print(out)
            return 0
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
