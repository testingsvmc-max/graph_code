#!/usr/bin/env python3
"""
Build a single interactive HTML file from a graph JSON or YAML export.

  python standalone_tools/export_code_graph_html.py graph.yaml -o graph.html

Optional: --edge-types CALLS,INCLUDES (comma) to reduce clutter.
Optional: --max-nodes N to cap nodes (keeps endpoints of selected edges first).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Export code graph YAML/JSON to interactive HTML (vis-network).")
    parser.add_argument("graph_file", type=Path, help="Path to graph .yaml / .yml / .json")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output .html path")
    parser.add_argument(
        "--edge-types",
        default=None,
        help="Comma-separated edge types to include (default: all). E.g. CALLS or CALLS,INCLUDES",
    )
    parser.add_argument("--max-nodes", type=int, default=None, help="Optional cap on number of nodes")
    parser.add_argument("--title", default=None, help="Browser title (default: input stem)")
    args = parser.parse_args()

    et = None
    if args.edge_types:
        et = {x.strip() for x in args.edge_types.split(",") if x.strip()}

    from code_graph_export.html_report import write_interactive_html_from_file

    write_interactive_html_from_file(
        str(args.graph_file.resolve()),
        str(args.output.resolve()),
        title=args.title,
        edge_types=et,
        max_nodes=args.max_nodes,
    )
    print(f"Wrote {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
