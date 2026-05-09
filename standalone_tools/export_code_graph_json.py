#!/usr/bin/env python3
"""
Export a code graph (nodes + edges) to JSON or YAML — no Neo4j.

Typical inputs (same as graph_builder.py):
  1. compile_commands.json (JSON compilation database)
  2. clangd-indexer YAML for the same tree

Example (after generating compile_commands.json and index YAML):

  python standalone_tools/export_code_graph_json.py \\
    path/to/clangd-index.yaml \\
    D:/GraphCode/android-wpa_supplicant-master/android-wpa_supplicant-master \\
    -o D:/GraphCode/android-wpa_supplicant-master/code_graph.json \\
    --compile-commands path/to/compile_commands.json

For the AOSP-style wpa_supplicant drop-in you still need a compilation database
for the files you want in the graph (CMake, Bear, compiledb, or an Android
Soong export). This script fails fast with a clear error if it is missing.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from pathlib import Path

# Repo root on sys.path when run as file
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import input_params
from log_manager import init_logging

logger = logging.getLogger(__name__)


def main() -> int:
    init_logging()
    parser = argparse.ArgumentParser(
        description="Export clangd + Clang-derived code graph to JSON or YAML (no Neo4j)."
    )
    input_params.add_core_input_args(parser)
    input_params.add_worker_args(parser)
    input_params.add_batching_args(parser)
    input_params.add_source_parser_args(parser)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path (e.g. code_graph.json or code_graph.yaml).",
    )
    parser.add_argument(
        "--format",
        choices=("json", "yaml", "auto"),
        default="auto",
        help="Output format: auto from -o extension (.yaml/.yml -> yaml), else json.",
    )

    args = parser.parse_args()

    from code_graph_export.memory_graph import build_code_graph_dict, write_code_graph_json, write_code_graph_yaml

    args.index_file = str(args.index_file.resolve())
    args.project_path = str(args.project_path.resolve())
    if args.ingest_batch_size is None:
        try:
            default_workers = math.ceil(os.cpu_count() / 2)
        except (NotImplementedError, TypeError):
            default_workers = 2
        nw = args.num_parse_workers or default_workers
        args.ingest_batch_size = args.cypher_tx_size * nw

    cc = args.compile_commands
    if cc:
        cc = str(Path(cc).resolve())
    else:
        cand = Path(args.project_path) / "compile_commands.json"
        if cand.is_file():
            cc = str(cand)
        else:
            logger.error(
                "No compile_commands.json found under project path and --compile-commands not set.\n"
                "Generate one for the tree you want to parse (e.g. Bear, CMake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON, "
                "or a Soong/NDK workflow that emits a compilation database), then re-run."
            )
            return 1

    if not Path(args.index_file).is_file():
        logger.error("Index file does not exist: %s", args.index_file)
        return 1

    graph = build_code_graph_dict(
        project_path=args.project_path,
        index_yaml_path=args.index_file,
        compile_commands_path=cc,
        num_parse_workers=args.num_parse_workers,
        log_batch_size=args.log_batch_size,
        ingest_batch_size=args.ingest_batch_size,
    )
    out = str(args.output.resolve())
    fmt = args.format
    if fmt == "auto":
        fmt = "yaml" if out.lower().endswith((".yaml", ".yml")) else "json"
    if fmt == "yaml":
        write_code_graph_yaml(graph, out)
    else:
        write_code_graph_json(graph, out)
    m = graph["meta"]
    logger.info("Done. Nodes: %s, edges: %s", len(graph["nodes"]), len(graph["edges"]))
    logger.info("By label: %s", m.get("node_counts_by_label"))
    logger.info("By edge type: %s", m.get("edge_counts_by_type"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
