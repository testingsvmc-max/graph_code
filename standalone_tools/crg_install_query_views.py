#!/usr/bin/env python3
"""
Add SQL views to an existing clangd-graph-rag ``graph.db`` for ad-hoc querying.

Views:
  v_calls          — CALLS edges with caller_qn / callee_qn
  v_callers_of     — callee → callers (for ``WHERE function_qn = ?``)
  v_callees_of     — caller → callees
  v_imports        — IMPORTS_FROM
  v_inherits       — INHERITS

Example:
  sqlite3 ".clangd-graph-rag/graph.db" "SELECT * FROM v_callers_of WHERE function_qn LIKE '%main%' LIMIT 20;"

  python standalone_tools/crg_install_query_views.py --db ".clangd-graph-rag/graph.db"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Install SQL query views on graph.db")
    p.add_argument("--db", type=Path, required=True)
    args = p.parse_args()

    from integrations.crg_sqlite import apply_views_to_file

    apply_views_to_file(args.db.resolve())
    print(f"Views installed on {args.db.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
