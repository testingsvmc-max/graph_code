#!/usr/bin/env python3
"""
Build clangd-graph-rag graph and export to SQLite ``graph.db`` (graph-review–compatible schema).

Example:
  python standalone_tools/export_code_graph_db.py index.yaml D:/myproj \
    --compile-commands D:/myproj/compile_commands.json \
    --db D:/myproj/.clangd-graph-rag/graph.db
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import input_params
from code_graph_export.memory_graph import build_code_graph_dict
from code_graph_export.sqlite_db import write_graph_sqlite
from log_manager import init_logging


def main() -> int:
    init_logging()
    p = argparse.ArgumentParser(description="Export clangd graph to SQLite graph.db (no Neo4j)")
    input_params.add_core_input_args(p)
    input_params.add_worker_args(p)
    input_params.add_batching_args(p)
    input_params.add_source_parser_args(p)
    p.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Output SQLite DB path (e.g. .clangd-graph-rag/graph.db)",
    )
    args = p.parse_args()

    index_file = Path(args.index_file).resolve()
    project_path = Path(args.project_path).resolve()
    if not index_file.is_file():
        print(f"Index file not found: {index_file}", file=sys.stderr)
        return 2
    if not project_path.is_dir():
        print(f"Project directory not found: {project_path}", file=sys.stderr)
        return 2

    cc = args.compile_commands
    if cc:
        cc = str(Path(cc).expanduser().resolve())
    else:
        cand = project_path / "compile_commands.json"
        if cand.is_file():
            cc = str(cand)
        else:
            print(
                "compile_commands.json not found. Pass --compile-commands or set COMPILE_COMMANDS_PATH.",
                file=sys.stderr,
            )
            return 2

    if args.ingest_batch_size is None:
        try:
            default_workers = math.ceil(os.cpu_count() / 2)
        except (NotImplementedError, TypeError):
            default_workers = 2
        nw = args.num_parse_workers or default_workers
        args.ingest_batch_size = args.cypher_tx_size * nw

    graph = build_code_graph_dict(
        project_path=str(project_path),
        index_yaml_path=str(index_file),
        compile_commands_path=cc,
        num_parse_workers=args.num_parse_workers,
        log_batch_size=args.log_batch_size,
        ingest_batch_size=args.ingest_batch_size,
    )
    out_db = write_graph_sqlite(graph, args.db)
    print(f"Wrote DB: {out_db}")
    print(f"Nodes: {len(graph.get('nodes') or [])}, Edges: {len(graph.get('edges') or [])}")
    print("Query examples:")
    print(f"  python standalone_tools/crg_db_query.py --db \"{out_db}\" search \"auth\"")
    print(f"  python standalone_tools/crg_db_query.py --db \"{out_db}\" callers \"<qualified_name>\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
