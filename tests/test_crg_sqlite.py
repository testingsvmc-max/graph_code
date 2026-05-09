"""Tests for clangd-graph-rag SQLite graph.db bridge (callers / callees / export)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# Repo root on path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from integrations.crg_sqlite import (
    call_graph_neighborhood,
    crg_db_to_export_dict,
    ensure_query_views,
    get_node_by_qualified_name,
    get_callers,
    get_callees,
    resolve_function_target,
    search_nodes,
)


def _create_minimal_crg_schema(conn: sqlite3.Connection) -> None:
    """Minimal subset of graph-review–compatible nodes/edges schema."""
    conn.executescript(
        """
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE nodes (
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
        CREATE TABLE edges (
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
    )
    # demo/f.py::main  -> calls -> demo/f.py::middle -> calls -> demo/f.py::leaf
    rows = [
        ("File", "f.py", "demo/f.py", "demo/f.py", 1, 100, "python", None, None, None, 0, None, "{}", 1.0),
        ("Function", "main", "demo/f.py::main", "demo/f.py", 10, 20, "python", None, "()", "None", 0, None, "{}", 1.0),
        ("Function", "middle", "demo/f.py::middle", "demo/f.py", 30, 40, "python", None, "()", "None", 0, None, "{}", 1.0),
        ("Function", "leaf", "demo/f.py::leaf", "demo/f.py", 50, 60, "python", None, "()", "None", 0, None, "{}", 1.0),
    ]
    conn.executemany(
        "INSERT INTO nodes (kind, name, qualified_name, file_path, line_start, line_end, "
        "language, parent_name, params, return_type, is_test, file_hash, extra, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    edges = [
        ("CALLS", "demo/f.py::main", "demo/f.py::middle", "demo/f.py", 12, "{}", 1.0, "EXTRACTED", 1.0),
        ("CALLS", "demo/f.py::middle", "demo/f.py::leaf", "demo/f.py", 35, "{}", 1.0, "EXTRACTED", 1.0),
    ]
    conn.executemany(
        "INSERT INTO edges (kind, source_qualified, target_qualified, file_path, line, "
        "extra, confidence, confidence_tier, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        edges,
    )
    conn.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '1')")
    conn.commit()


@pytest.fixture()
def crg_conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "graph.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    _create_minimal_crg_schema(conn)
    return conn


def test_get_callees_main(crg_conn: sqlite3.Connection) -> None:
    rows = get_callees(crg_conn, "demo/f.py::main")
    assert len(rows) == 1
    assert rows[0]["callee_qn"] == "demo/f.py::middle"


def test_get_callers_middle(crg_conn: sqlite3.Connection) -> None:
    rows = get_callers(crg_conn, "demo/f.py::middle")
    assert len(rows) == 1
    assert rows[0]["caller_qn"] == "demo/f.py::main"


def test_get_callers_leaf(crg_conn: sqlite3.Connection) -> None:
    rows = get_callers(crg_conn, "demo/f.py::leaf")
    assert len(rows) == 1
    assert rows[0]["caller_qn"] == "demo/f.py::middle"


def test_get_callees_middle(crg_conn: sqlite3.Connection) -> None:
    rows = get_callees(crg_conn, "demo/f.py::middle")
    assert len(rows) == 1
    assert rows[0]["callee_qn"] == "demo/f.py::leaf"


def test_crg_db_to_export_dict_calls_edges(crg_conn: sqlite3.Connection) -> None:
    data = crg_db_to_export_dict(crg_conn, edge_kinds={"CALLS"})
    call_edges = [e for e in data["edges"] if e["type"] == "CALLS"]
    assert len(call_edges) == 2
    pairs = {(e["src"], e["dst"]) for e in call_edges}
    assert ("demo/f.py::main", "demo/f.py::middle") in pairs
    assert ("demo/f.py::middle", "demo/f.py::leaf") in pairs


def test_views_idempotent(crg_conn: sqlite3.Connection) -> None:
    ensure_query_views(crg_conn)
    ensure_query_views(crg_conn)
    assert len(get_callers(crg_conn, "demo/f.py::leaf")) == 1


def test_stub_missing_call_target(crg_conn: sqlite3.Connection) -> None:
    crg_conn.execute(
        "INSERT INTO edges (kind, source_qualified, target_qualified, file_path, line, "
        "extra, confidence, confidence_tier, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("CALLS", "demo/f.py::main", "other/file.c::ghost", "demo/f.py", 11, "{}", 1.0, "EXTRACTED", 1.0),
    )
    crg_conn.commit()
    data = crg_db_to_export_dict(crg_conn, edge_kinds={"CALLS"}, stub_missing_call_targets=False)
    pairs = {(e["src"], e["dst"]) for e in data["edges"]}
    assert ("demo/f.py::main", "other/file.c::ghost") not in pairs
    data2 = crg_db_to_export_dict(crg_conn, edge_kinds={"CALLS"}, stub_missing_call_targets=True)
    pairs2 = {(e["src"], e["dst"]) for e in data2["edges"]}
    assert ("demo/f.py::main", "other/file.c::ghost") in pairs2
    ids = {n["id"] for n in data2["nodes"]}
    assert "other/file.c::ghost" in ids


def test_search_nodes(crg_conn: sqlite3.Connection) -> None:
    rows = search_nodes(crg_conn, "main")
    assert rows
    assert any(r["qualified_name"] == "demo/f.py::main" for r in rows)


def test_resolve_function_target_ok_and_ambiguous(crg_conn: sqlite3.Connection) -> None:
    ok = resolve_function_target(crg_conn, "demo/f.py::main")
    assert ok["status"] == "ok"
    assert ok["node"]["qualified_name"] == "demo/f.py::main"

    # Add another "main" to force ambiguity by short name.
    crg_conn.execute(
        "INSERT INTO nodes (kind, name, qualified_name, file_path, line_start, line_end, "
        "language, parent_name, params, return_type, is_test, file_hash, extra, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("Function", "main", "demo/g.py::main", "demo/g.py", 1, 2, "python", None, "()", "None", 0, None, "{}", 1.0),
    )
    crg_conn.commit()
    amb = resolve_function_target(crg_conn, "main")
    assert amb["status"] == "ambiguous"
    assert len(amb["candidates"]) >= 2


def test_call_graph_neighborhood(crg_conn: sqlite3.Connection) -> None:
    out = call_graph_neighborhood(crg_conn, "demo/f.py::main", direction="down", depth=2, limit=20)
    qns = {n["qualified_name"] for n in out["nodes"]}
    assert "demo/f.py::main" in qns
    assert "demo/f.py::middle" in qns
    assert "demo/f.py::leaf" in qns
    pairs = {(e["src"], e["dst"]) for e in out["edges"]}
    assert ("demo/f.py::main", "demo/f.py::middle") in pairs
    assert ("demo/f.py::middle", "demo/f.py::leaf") in pairs


def test_get_node_by_qualified_name(crg_conn: sqlite3.Connection) -> None:
    n = get_node_by_qualified_name(crg_conn, "demo/f.py::leaf")
    assert n is not None
    assert n["name"] == "leaf"


def test_get_callees_returns_cross_file_file_path(crg_conn: sqlite3.Connection) -> None:
    # Add a function in another file and connect main -> helper.
    crg_conn.execute(
        "INSERT INTO nodes (kind, name, qualified_name, file_path, line_start, line_end, "
        "language, parent_name, params, return_type, is_test, file_hash, extra, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("Function", "helper", "demo/g.py::helper", "demo/g.py", 5, 10, "python", None, "()", "None", 0, None, "{}", 1.0),
    )
    crg_conn.execute(
        "INSERT INTO edges (kind, source_qualified, target_qualified, file_path, line, "
        "extra, confidence, confidence_tier, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("CALLS", "demo/f.py::main", "demo/g.py::helper", "demo/f.py", 15, "{}", 1.0, "EXTRACTED", 1.0),
    )
    crg_conn.commit()

    rows = get_callees(crg_conn, "demo/f.py::main")
    match = next((r for r in rows if r["callee_qn"] == "demo/g.py::helper"), None)
    assert match is not None
    assert match["file_path"] == "demo/g.py"
