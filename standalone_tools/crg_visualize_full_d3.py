#!/usr/bin/env python3
"""
Regenerate D3 HTML in **full** symbol mode (includes CALLS edges), then apply
cross-file CALL highlighting (``crg_d3_postprocess``).

Default ``visualize --mode auto`` often switches to **community** aggregation when
the node count exceeds a threshold — that embeds no per-function CALL edges, so
cross-file call arcs cannot appear.

  python standalone_tools/crg_visualize_full_d3.py --db path/to/graph.db -o graph_d3.html

Requires the optional upstream visualize helpers (``GraphStore``, ``generate_html``);
see README for install notes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from log_manager import init_logging


def main() -> int:
    init_logging()
    p = argparse.ArgumentParser(
        description="Write D3 HTML in full mode + cross-file CALL styling"
    )
    p.add_argument("--db", type=Path, required=True, help="Path to graph.db")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path for enhanced D3 HTML (e.g. graph_d3.html)",
    )
    p.add_argument(
        "--no-legend",
        action="store_true",
        help="Do not inject Vietnamese legend (passed to enhancer)",
    )
    args = p.parse_args()

    try:
        from code_review_graph.graph import GraphStore
        from code_review_graph.visualization import generate_html
    except ImportError as exc:
        print(
            "Missing optional visualize package (provides GraphStore, generate_html). "
            "See README; PyPI package name may differ from this repo.",
            file=sys.stderr,
        )
        print(exc, file=sys.stderr)
        return 2

    from code_graph_export.crg_d3_postprocess import enhance_crg_d3_html

    db = args.db.resolve()
    outp = args.output.resolve()
    outp.parent.mkdir(parents=True, exist_ok=True)

    store = GraphStore(db)
    try:
        generate_html(store, outp, mode="full")
    finally:
        store.close()

    enhance_crg_d3_html(outp, outp, inject_legend=not args.no_legend)
    print(f"OK: {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
