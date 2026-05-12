"""Write clangd-graph-rag export dict to SQLite ``graph.db`` (graph-review–compatible schema)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Union


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    language TEXT,
    parent_name TEXT,
    params TEXT,
    return_type TEXT,
    modifiers TEXT,
    is_test INTEGER DEFAULT 0,
    file_hash TEXT,
    extra TEXT DEFAULT '{}',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    source_qualified TEXT NOT NULL,
    target_qualified TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line INTEGER DEFAULT 0,
    extra TEXT DEFAULT '{}',
    confidence REAL DEFAULT 1.0,
    confidence_tier TEXT DEFAULT 'EXTRACTED',
    updated_at REAL NOT NULL
);
"""


def _pick_kind(n: Dict[str, Any]) -> str:
    labels = n.get("labels") or []
    if labels:
        return str(labels[0])
    return "Unknown"


def _norm_fp(v: Any) -> str:
    if v is None:
        return ""
    return str(v).replace("\\", "/")


def write_graph_sqlite(graph: Dict[str, Any], db_path: Union[str, Path]) -> Path:
    """
    Persist graph export dict into SQLite ``graph.db`` (same core tables as common graph-review tooling).
    Returns resolved DB path.
    """
    db = Path(db_path).expanduser().resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(_SCHEMA_SQL)
        now = time.time()

        # Reset content for deterministic rebuilds.
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM nodes")
        conn.execute("DELETE FROM metadata")

        symbol_to_file: Dict[str, str] = {}
        for e in graph.get("edges") or []:
            if str(e.get("type") or "") != "DEFINES":
                continue
            src = str(e.get("src") or "")
            dst = str(e.get("dst") or "")
            if not src or not dst:
                continue
            if src.startswith("file:"):
                rel = _norm_fp(src[len("file:") :])
                if rel:
                    symbol_to_file[dst] = rel

        nodes_insert = []
        for n in graph.get("nodes") or []:
            props = n.get("properties") or {}
            qn = str(n.get("id") or "")
            if not qn:
                continue
            name = str(props.get("name") or qn.split("::")[-1] or qn)
            kind = _pick_kind(n)
            node_fp = _norm_fp(props.get("path") or props.get("file_path")) or symbol_to_file.get(qn, "")
            nodes_insert.append(
                (
                    kind,
                    name,
                    qn,
                    node_fp,
                    props.get("line_start"),
                    props.get("line_end"),
                    props.get("language"),
                    props.get("parent_name"),
                    props.get("params"),
                    props.get("return_type"),
                    props.get("modifiers"),
                    1 if bool(props.get("is_test")) else 0,
                    props.get("file_hash"),
                    json.dumps(props, ensure_ascii=False),
                    now,
                )
            )

        conn.executemany(
            "INSERT INTO nodes (kind,name,qualified_name,file_path,line_start,line_end,language,"
            "parent_name,params,return_type,modifiers,is_test,file_hash,extra,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            nodes_insert,
        )

        edges_insert = []
        for e in graph.get("edges") or []:
            et = str(e.get("type") or "")
            src = str(e.get("src") or "")
            dst = str(e.get("dst") or "")
            if not et or not src or not dst:
                continue
            props = e.get("properties") or {}
            edge_fp = _norm_fp(props.get("file_path"))
            if not edge_fp and et == "CALLS":
                edge_fp = symbol_to_file.get(src, "")
            edges_insert.append(
                (
                    et,
                    src,
                    dst,
                    edge_fp,
                    int(props.get("line") or 0),
                    json.dumps(props, ensure_ascii=False),
                    float(props.get("confidence") or 1.0),
                    str(props.get("confidence_tier") or "EXTRACTED"),
                    now,
                )
            )
        conn.executemany(
            "INSERT INTO edges (kind,source_qualified,target_qualified,file_path,line,extra,confidence,confidence_tier,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            edges_insert,
        )

        meta = dict(graph.get("meta") or {})
        meta.setdefault("source", "clangd-graph-rag")
        meta_rows = [("schema_version", "1")]
        for k, v in meta.items():
            meta_rows.append((str(k), json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v))
        conn.executemany("INSERT INTO metadata (key,value) VALUES (?,?)", meta_rows)
        conn.commit()
    finally:
        conn.close()
    return db
