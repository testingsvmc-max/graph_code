"""
clangd-graph-rag **SQLite graph.db** adapter (shared ``nodes`` / ``edges`` schema).

Typical path for a DB produced by this repo: ``<project>/.clangd-graph-rag/graph.db``.
The layout matches the common graph-review SQLite shape (qualified names, ``CALLS``,
``INCLUDES``, …) so the same SQL views and HTML exporters apply.

This module does **not** import third-party graph-review Python packages; it only
uses ``sqlite3``.

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
        SELECT c.caller_qn, c.line, COALESCE(n.file_path, c.file_path, '') AS file_path
        FROM v_callers_of c
        LEFT JOIN nodes n ON n.qualified_name = c.caller_qn
        WHERE c.function_qn = ?
        ORDER BY c.caller_qn
        """,
        (callee_qualified_name,),
    )
    return [_row_to_dict(r) for r in cur.fetchall()]


def get_callees(conn: sqlite3.Connection, caller_qualified_name: str) -> List[Dict[str, Any]]:
    """Return rows ``{callee_qn, line, file_path}`` for ``CALLS`` from *caller_qualified_name*."""
    ensure_query_views(conn)
    cur = conn.execute(
        """
        SELECT c.callee_qn, c.line, COALESCE(n.file_path, c.file_path, '') AS file_path
        FROM v_callees_of c
        LEFT JOIN nodes n ON n.qualified_name = c.callee_qn
        WHERE c.function_qn = ?
        ORDER BY c.callee_qn
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
    Map SQLite ``nodes`` / ``edges`` into the export schema used by
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

    meta = {"source": "clangd-graph-rag"}
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


def search_nodes(
    conn: sqlite3.Connection,
    query: str,
    *,
    kinds: Optional[Set[str]] = None,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Search nodes by name / qualified_name / file_path."""
    q = (query or "").strip().lower()
    if not q:
        return []
    kinds = kinds or {"Function", "Method", "FUNCTION", "METHOD"}
    expanded_kinds = set()
    for k in kinds:
        expanded_kinds.add(k)
        expanded_kinds.add(k.upper())
        expanded_kinds.add(k.capitalize())
    placeholders = ",".join("?" for _ in sorted(expanded_kinds))
    sql = (
        "SELECT kind, name, qualified_name, file_path, line_start, line_end, language "
        "FROM nodes "
        f"WHERE kind IN ({placeholders}) "
        "AND (lower(name) LIKE ? OR lower(qualified_name) LIKE ? OR lower(file_path) LIKE ?) "
        "ORDER BY name, qualified_name LIMIT ?"
    )
    like = f"%{q}%"
    params: List[Any] = [*sorted(expanded_kinds), like, like, like, max(1, int(limit))]
    cur = conn.execute(sql, params)
    return [_row_to_dict(r) for r in cur.fetchall()]


def get_node_by_qualified_name(conn: sqlite3.Connection, qualified_name: str) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        "SELECT kind, name, qualified_name, file_path, line_start, line_end, language "
        "FROM nodes WHERE qualified_name = ? LIMIT 1",
        (qualified_name,),
    )
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


def resolve_function_target(conn: sqlite3.Connection, target: str, *, limit: int = 10) -> Dict[str, Any]:
    """
    Resolve query target to one function/method node.
    Returns dict with keys: status (ok|not_found|ambiguous), node/candidates.
    """
    node = get_node_by_qualified_name(conn, target)
    if node and str(node.get("kind") or "").upper() in {"FUNCTION", "METHOD"}:
        return {"status": "ok", "node": node}

    candidates = search_nodes(conn, target, kinds={"Function", "Method", "FUNCTION", "METHOD"}, limit=limit)
    qn_exact = [x for x in candidates if (x.get("qualified_name") or "").lower() == target.lower()]
    if len(qn_exact) == 1:
        return {"status": "ok", "node": qn_exact[0]}
    if not candidates:
        return {"status": "not_found", "target": target}
    if len(candidates) == 1:
        return {"status": "ok", "node": candidates[0]}
    return {"status": "ambiguous", "target": target, "candidates": candidates}


def call_graph_neighborhood(
    conn: sqlite3.Connection,
    center_qn: str,
    *,
    direction: str = "both",
    depth: int = 1,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    BFS over CALLS edges around center function.
    direction: up (callers), down (callees), both.
    """
    direction = (direction or "both").lower()
    if direction not in {"up", "down", "both"}:
        raise ValueError("direction must be one of: up, down, both")
    depth = max(1, int(depth))
    limit = max(1, int(limit))

    seen: Set[str] = {center_qn}
    edges: List[Dict[str, str]] = []

    def _down(frontier: Set[str]) -> Set[str]:
        nxt: Set[str] = set()
        for src in frontier:
            cur = conn.execute(
                "SELECT target_qualified AS qn FROM edges WHERE kind='CALLS' AND source_qualified=?",
                (src,),
            )
            for r in cur.fetchall():
                dst = r["qn"]
                edges.append({"type": "CALLS", "src": src, "dst": dst})
                if dst not in seen and len(seen) < limit:
                    seen.add(dst)
                    nxt.add(dst)
        return nxt

    def _up(frontier: Set[str]) -> Set[str]:
        nxt: Set[str] = set()
        for dst in frontier:
            cur = conn.execute(
                "SELECT source_qualified AS qn FROM edges WHERE kind='CALLS' AND target_qualified=?",
                (dst,),
            )
            for r in cur.fetchall():
                src = r["qn"]
                edges.append({"type": "CALLS", "src": src, "dst": dst})
                if src not in seen and len(seen) < limit:
                    seen.add(src)
                    nxt.add(src)
        return nxt

    if direction in {"down", "both"}:
        frontier = {center_qn}
        for _ in range(depth):
            frontier = _down(frontier)
            if not frontier:
                break

    if direction in {"up", "both"}:
        frontier = {center_qn}
        for _ in range(depth):
            frontier = _up(frontier)
            if not frontier:
                break

    nodes: List[Dict[str, Any]] = []
    for qn in sorted(seen):
        n = get_node_by_qualified_name(conn, qn)
        if n:
            nodes.append(n)
        else:
            nodes.append(
                {
                    "kind": "UNRESOLVED_CALL_TARGET",
                    "name": qn.split("::")[-1],
                    "qualified_name": qn,
                    "file_path": "",
                }
            )

    uniq: List[Dict[str, str]] = []
    seen_e: Set[tuple[str, str, str]] = set()
    for e in edges:
        k = (e["src"], e["dst"], e["type"])
        if k in seen_e:
            continue
        seen_e.add(k)
        uniq.append(e)
    return {"center": center_qn, "direction": direction, "depth": depth, "nodes": nodes, "edges": uniq}
