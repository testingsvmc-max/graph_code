#!/usr/bin/env python3
"""
Ingest a clangd index produced on another machine into Neo4j (and optional RAG) using a local checkout.

Typical Windows workflow:

1. Copy ``index.yaml`` (clangd --project-index) from the server and place it locally.
2. ``compile_commands.json`` may still list Linux ``/home/...`` paths if it was copied from the server; with ``--index-source-root`` the pipeline rewrites it to your Windows tree (same as ``graph_builder``). Regenerating ``compile_commands.json`` on Windows is still recommended when possible.
3. Run this repo's full pipeline with path rewrite:

   python standalone_tools/ingest_server_index_local.py ^
     path\\to\\server_index.yaml D:\\GraphCode\\myrepo ^
     --compile-commands D:\\GraphCode\\myrepo\\build\\compile_commands.json ^
     --index-source-root /home/ci/workspace/myrepo

``--index-source-root`` must be the absolute root that appears inside the YAML ``FileURI`` values from the server.
``--local-source-root`` defaults to the second positional argument (your Windows project root).

Outputs (same as ``graph_builder.py``):

- Neo4j graph DB (nodes/relationships)
- With ``--generate-summary``: embeddings stored on graph nodes (see summary_driver)

SQLite export / FAISS (optional follow-up)::

   python standalone_tools/build_graph_code.py D:\\GraphCode\\myrepo --index-file ... --also-db
   python standalone_tools/faiss_code_graph_index.py build --graph D:\\GraphCode\\myrepo\\.clangd-graph-rag\\code_graph.yaml --out-dir D:\\embed_out
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    import input_params
    from graph_builder import GraphBuilder

    parser = argparse.ArgumentParser(
        description="Wrapper around graph_builder for server YAML + local Windows (or any) tree."
    )
    input_params.add_core_input_args(parser)
    input_params.add_cross_machine_path_args(parser)
    input_params.add_worker_args(parser)
    input_params.add_batching_args(parser)
    input_params.add_rag_args(parser)
    input_params.add_llm_cache_args(parser)
    input_params.add_ingestion_strategy_args(parser)
    input_params.add_source_parser_args(parser)
    input_params.add_logistic_args(parser)
    parser.add_argument(
        "--new-commit",
        default=None,
        help="Commit hash/reference for graph stamp (default: repo HEAD)",
    )
    args = parser.parse_args()

    args.index_file = str(Path(args.index_file).resolve())
    args.project_path = str(Path(args.project_path).resolve())

    if args.ingest_batch_size is None:
        import math

        try:
            default_workers = math.ceil(os.cpu_count() / 2)
        except (NotImplementedError, TypeError):
            default_workers = 2
        args.ingest_batch_size = args.cypher_tx_size * (args.num_parse_workers or default_workers)

    return GraphBuilder(args).build()


if __name__ == "__main__":
    raise SystemExit(main())
