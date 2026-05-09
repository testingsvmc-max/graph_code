#!/usr/bin/env python3
"""
Enhance D3 graph HTML so cross-file CALL edges (hàm file X → hàm file Y) show in orange.

  python standalone_tools/crg_enhance_d3_html.py path/to/graph.html
  python standalone_tools/crg_enhance_d3_html.py path/to/graph.html -o path/out.html

Typical after generating ``graph.html`` with a full-mode visualize step (use
``--mode full`` if the repo has many nodes — default ``auto`` switches to **community**
mode, which has no ``CALLS`` edges in the embedded JSON; see README):

    python standalone_tools/crg_enhance_d3_html.py \\
    path/to/repo/.clangd-graph-rag/graph.html -o path/to/graph_d3.html

Or generate full-mode D3 and enhance in one step:

    python standalone_tools/crg_visualize_full_d3.py --db path/to/graph.db -o graph_d3.html
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from log_manager import init_logging


def main() -> int:
    init_logging()
    p = argparse.ArgumentParser(description="Enhance D3 graph HTML: highlight cross-file CALL edges")
    p.add_argument("input_html", type=Path, help="graph.html from a visualize/export step")
    p.add_argument("-o", "--output", type=Path, default=None, help="Output path (default: overwrite input)")
    p.add_argument("--no-legend", action="store_true", help="Do not inject Vietnamese legend box")
    args = p.parse_args()

    from code_graph_export.crg_d3_postprocess import enhance_crg_d3_html

    outp = enhance_crg_d3_html(
        args.input_html,
        args.output,
        inject_legend=not args.no_legend,
    )
    print(f"OK: {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
