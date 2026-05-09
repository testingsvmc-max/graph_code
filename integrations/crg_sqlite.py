"""
code-review-graph (CRG) SQLite adapter — review notes + helpers.

Upstream layout (tirth8205/code-review-graph):
  - Default DB: ``<repo>/.code-review-graph/graph.db``
  - Core tables: ``nodes`` (kind, name, qualified_name UNIQUE, file_path, …),
    ``edges`` (kind, source_qualified, target_qualified, file_path, line, …)
  - Build: ``code-review-graph build`` (Tree-sitter parse → SQLite)
  - HTML (D3): ``code-review-graph visualize`` → ``.code-review-graph/graph.html``

This module does *not* import ``code_review_graph``; it only reads SQLite so you
can use it from this repo after a CRG build, or copy the DB elsewhere.

Provides:
  - ``ensure_query_views(conn)`` — views for callers / callees / imports (SQL)
  - ``get_callers(conn, callee_qn)`` / ``get_callees(conn, caller_qn)`` — row dicts
  - ``crg_db_to_export_dict(conn, edge_kinds=...)`` — export shape for vis-network HTML
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# SQL views (idempotent) — run against an existing graph.db
# ---------------------------------------------------------------------------

_VIEWS_SQL = """
CREATE VIEW IF NOT EXISTS v_calls AS
SELECT id, source_qualified AS caller_qn, target_qualified AS callee_qn,
       file_path, line, confidence
FROM edges WHERE kind = 'CALLS';

CREATE VIEW IF NOT EXISTS v_imports AS
SELECT id, source_qualified AS importer_qn, target_qualified AS imported_qn,
       file_path, line
FROM edges WHERE kind = 'IMPORTS_FROM';

CREATE VIEW IF NOT EXISTS v_inherits AS
SELECT id, source_qualified AS child_qn, target_qualified AS parent_qn,
       file_path, line
FROM edges WHERE kind = 'INHERITS';

CREATE VIEW IF NOT EXISTS v_callers_of AS
SELECT target_qualified AS function_qn, source_qualified AS caller_qn, line, file_path
FROM edges WHERE kind = 'CALLS';

CREATE VIEW IF NOT EXISTS v_callees_of AS
SELECT source_qualified AS function_qn, target_qualified AS callee_qn, line, file_path
FROM edges WHERE kind = 'CALLS';
"""


def ensure_query_views(conn: sqlite3.Connection) -> None:
    """Create helper views for interactive querying (sqlite3 / DB Browser)."""
    conn.executescript(_VIEWS_SQL)
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def get_callers(conn: sqlite3.Connection, callee_qualified_name: str) -> List[Dict[str, Any]]:
    """Return rows ``{caller_qn, line, file_path}`` for ``CALLS`` into *callee_qualified_name*."""
    ensure_query_views(conn)
    cur = conn.execute(
        """
        SELECT caller_qn, line, file_path
        FROM v_callers_of
        WHERE function_qn = ?
        ORDER BY caller_qn
        """,
        (callee_qualified_name,),
    )
    return [_row_to_dict(r) for r in cur.fetchall()]


def get_callees(conn: sqlite3.Connection, caller_qualified_name: str) -> List[Dict[str, Any]]:
    """Return rows ``{callee_qn, line, file_path}`` for ``CALLS`` from *caller_qualified_name*."""
    ensure_query_views(conn)
    cur = conn.execute(
        """
        SELECT callee_qn, line, file_path
        FROM v_callees_of
        WHERE function_qn = ?
        ORDER BY callee_qn
        """,
        (caller_qualified_name,),
    )
    return [_row_to_dict(r) for r in cur.fetchall()]


def load_crg_db(db_path: str | Path) -> sqlite3.Connection:
    p = Path(db_path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"graph.db not found: {p}")
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def crg_db_to_export_dict(
    conn: sqlite3.Connection,
    *,
    edge_kinds: Optional[Set[str]] = None,
    node_kinds: Optional[Set[str]] = None,
    stub_missing_call_targets: bool = False,
) -> Dict[str, Any]:
    """
    Map CRG ``nodes`` / ``edges`` into the export schema used by
    ``code_graph_export.html_report.write_interactive_html``.

    Node ``id`` is ``qualified_name`` (matches edge endpoints).

    If ``stub_missing_call_targets`` is True, for ``CALLS`` whose callee
    qualified name has no ``nodes`` row (common in C: macros, unresolved
    symbols, stdlib), a synthetic node is added so the edge still appears in
    HTML exports.
    """
    if edge_kinds is None:
        edge_kinds = {
            "CALLS",
            "IMPORTS_FROM",
            "INHERITS",
            "IMPLEMENTS",
            "CONTAINS",
            "REFERENCES",
            "DEPENDS_ON",
            "TESTED_BY",
        }
    nodes: List[Dict[str, Any]] = []
    qn_set: Set[str] = set()

    cur = conn.execute(
        "SELECT kind, name, qualified_name, file_path, line_start, line_end, "
        "language, parent_name, params, return_type, is_test FROM nodes"
    )
    for row in cur:
        kind = row["kind"] or "Unknown"
        if node_kinds is not None and kind not in node_kinds:
            continue
        qn = row["qualified_name"]
        if not qn:
            continue
        qn_set.add(qn)
        nodes.append(
            {
                "id": qn,
                "labels": [kind],
                "properties": {
                    "name": row["name"],
                    "qualified_name": qn,
                    "file_path": row["file_path"],
                    "line_start": row["line_start"],
                    "line_end": row["line_end"],
                    "language": row["language"],
                    "parent_name": row["parent_name"],
                    "params": row["params"],
                    "return_type": row["return_type"],
                    "is_test": bool(row["is_test"]),
                },
            }
        )

    edges: List[Dict[str, Any]] = []
    ec = conn.execute(
        "SELECT kind, source_qualified, target_qualified, file_path, line, confidence "
        "FROM edges"
    )
    stub_added: Set[str] = set()
    for row in ec:
        k = row["kind"] or ""
        if k not in edge_kinds:
            continue
        src, dst = row["source_qualified"], row["target_qualified"]
        if src not in qn_set:
            continue
        if dst not in qn_set:
            if stub_missing_call_targets and k == "CALLS":
                if dst not in stub_added:
                    stub_added.add(dst)
                    stub_fp = ""
                    if "::" in dst:
                        pref = dst.rsplit("::", 1)[0]
                        if pref and ("/" in pref or "\\" in pref or pref.endswith((".c", ".h", ".cc", ".cpp", ".hh"))):
                            stub_fp = pref.replace("\\", "/")
                    nodes.append(
                        {
                            "id": dst,
                            "labels": ["UNRESOLVED_CALL_TARGET"],
                            "properties": {
                                "name": dst.split("::")[-1] if "::" in dst else dst,
                                "qualified_name": dst,
                                "file_path": stub_fp or None,
                                "note": "No matching node in graph (macro / external / parser gap)",
                            },
                        }
                    )
                    qn_set.add(dst)
            else:
                continue
        edges.append(
            {
                "type": k,
                "src": src,
                "dst": dst,
                "properties": {
                    "file_path": row["file_path"],
                    "line": row["line"],
                    "confidence": row["confidence"],
                },
            }
        )

    def _norm_fp(fp: Optional[str]) -> str:
        if not fp:
            return ""
        return str(fp).replace("\\", "/").lower()

    qn_to_fp: Dict[str, str] = {}
    for n in nodes:
        qn_to_fp[n["id"]] = _norm_fp((n.get("properties") or {}).get("file_path"))

    for e in edges:
        if e.get("type") != "CALLS":
            continue
        fp_s = qn_to_fp.get(e["src"], "")
        fp_t = qn_to_fp.get(e["dst"], "")
        if fp_s and fp_t and fp_s != fp_t:
            e["properties"]["cross_file"] = True

    meta = {"source": "code-review-graph"}
    try:
        row = conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()
        if row:
            meta["crg_schema_version"] = row[0]
    except sqlite3.OperationalError:
        pass

    return {"meta": meta, "nodes": nodes, "edges": edges}


def apply_views_to_file(db_path: str | Path) -> None:
    """CLI helper: open DB, create views, close."""
    conn = load_crg_db(db_path)
    try:
        ensure_query_views(conn)
    finally:
        conn.close()
