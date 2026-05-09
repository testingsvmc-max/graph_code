#!/usr/bin/env python3
"""
Read a clangd-graph-rag SQLite ``graph.db`` (nodes/edges; graph-review–compatible schema)
and write a vis-network HTML file.

Schema lineage and related tooling are documented in the README; this script is an
alternative HTML export (same engine as ``export_code_graph_html.py``).

Example:
  python standalone_tools/crg_db_to_vis_html.py ^
    --db "D:\\myrepo\\.clangd-graph-rag\\graph.db" ^
    -o "D:\\myrepo\\.clangd-graph-rag\\graph_vis.html" ^
    --edge-kinds CALLS,IMPORTS_FROM
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="graph.db → vis-network HTML")
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to graph.db (clangd-graph-rag export)",
    )
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output .html")
    parser.add_argument(
        "--edge-kinds",
        default="CALLS,IMPORTS_FROM,INHERITS",
        help="Comma-separated edge kinds to include",
    )
    parser.add_argument("--max-nodes", type=int, default=None)
    parser.add_argument(
        "--views",
        action="store_true",
        help="Also create SQL views (v_calls, v_callers_of, …) inside the DB file",
    )
    parser.add_argument(
        "--stub-missing-call-targets",
        action="store_true",
        help="Add placeholder nodes for CALLS whose callee has no nodes row (large HTML; see README)",
    )
    parser.add_argument(
        "--inter-file-full",
        action="store_true",
        help="Shortcut: --edge-kinds CALLS --stub-missing-call-targets --max-nodes 25000 (gọi liên file + callee thiếu node)",
    )
    args = parser.parse_args()

    if args.inter_file_full:
        args.edge_kinds = "CALLS"
        args.stub_missing_call_targets = True
        if args.max_nodes is None:
            args.max_nodes = 25000

    kinds = {x.strip() for x in args.edge_kinds.split(",") if x.strip()}

    from integrations.crg_sqlite import crg_db_to_export_dict, ensure_query_views, load_crg_db
    from code_graph_export.html_report import write_interactive_html

    conn = load_crg_db(args.db)
    try:
        if args.views:
            ensure_query_views(conn)
        graph = crg_db_to_export_dict(
            conn,
            edge_kinds=kinds,
            stub_missing_call_targets=args.stub_missing_call_targets,
        )
    finally:
        conn.close()

    write_interactive_html(
        graph,
        str(args.output.resolve()),
        title=args.db.stem,
        edge_types=kinds,
        max_nodes=args.max_nodes,
    )
    print(f"Wrote {args.output.resolve()}")
    if args.views:
        print("Query views installed on DB (v_calls, v_callers_of, v_callees_of, …)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
