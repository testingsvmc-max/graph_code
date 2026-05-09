#!/usr/bin/env python3
"""
MR / CI helper: install SQL views, print caller/callee probe, optional vis-network HTML.

Requires a clangd-graph-rag SQLite ``graph.db`` (see ``export_code_graph_db``).

  python standalone_tools/crg_mr_pipeline.py --db path/to/.clangd-graph-rag/graph.db
  python standalone_tools/crg_mr_pipeline.py --db path/to/graph.db --html out.html --center "demo/f.py::main"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="graph.db: views + caller/callee probe + optional HTML")
    p.add_argument("--db", type=Path, required=True, help="Path to graph.db")
    p.add_argument(
        "--center",
        type=str,
        default=None,
        help="Qualified name of a function to query (default: first Function row in DB)",
    )
    p.add_argument("--html", type=Path, default=None, help="Write vis-network HTML to this path")
    p.add_argument(
        "--inter-file-full",
        action="store_true",
        help="When exporting HTML: CALLS + stub missing callees + cap 25k nodes (see crg_db_to_vis_html)",
    )
    p.add_argument("--edge-kinds", default="CALLS,IMPORTS_FROM,INHERITS", help="For HTML export")
    args = p.parse_args()

    from integrations.crg_sqlite import (
        crg_db_to_export_dict,
        ensure_query_views,
        get_callers,
        get_callees,
        load_crg_db,
    )

    conn = load_crg_db(args.db.resolve())
    try:
        ensure_query_views(conn)

        center = args.center
        if not center:
            row = conn.execute(
                "SELECT qualified_name FROM nodes WHERE kind = 'Function' ORDER BY qualified_name LIMIT 1"
            ).fetchone()
            if not row:
                print("No Function nodes in DB; pass --center explicitly", file=sys.stderr)
                return 2
            center = row[0]

        callers = get_callers(conn, center)
        callees = get_callees(conn, center)
        report = {
            "db": str(args.db.resolve()),
            "center": center,
            "caller_count": len(callers),
            "callee_count": len(callees),
            "callers": callers,
            "callees": callees,
        }
        print(json.dumps(report, indent=2))

        if args.html:
            if args.inter_file_full:
                args.edge_kinds = "CALLS"
            kinds = {x.strip() for x in args.edge_kinds.split(",") if x.strip()}
            graph = crg_db_to_export_dict(
                conn,
                edge_kinds=kinds,
                stub_missing_call_targets=bool(args.inter_file_full),
            )
            from code_graph_export.html_report import write_interactive_html

            write_interactive_html(
                graph,
                str(args.html.resolve()),
                title=center[:40],
                edge_types=kinds,
                max_nodes=25000 if args.inter_file_full else None,
            )
            print(f"HTML: {args.html.resolve()}", file=sys.stderr)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
