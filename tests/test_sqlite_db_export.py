"""Tests for SQLite export file-path backfill from DEFINES edges."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code_graph_export.sqlite_db import write_graph_sqlite
from integrations.crg_sqlite import get_callers


def test_write_graph_sqlite_backfills_symbol_and_call_file_paths(tmp_path: Path) -> None:
    graph = {
        "meta": {"project_path": "demo"},
        "nodes": [
            {"id": "file:src/a.c", "labels": ["FILE"], "properties": {"path": "src/a.c", "name": "a.c"}},
            {"id": "file:src/b.c", "labels": ["FILE"], "properties": {"path": "src/b.c", "name": "b.c"}},
            {"id": "A_FN", "labels": ["FUNCTION"], "properties": {"name": "a_fn", "kind": "FUNCTION"}},
            {"id": "B_FN", "labels": ["FUNCTION"], "properties": {"name": "b_fn", "kind": "FUNCTION"}},
        ],
        "edges": [
            {"type": "DEFINES", "src": "file:src/a.c", "dst": "A_FN", "properties": {"symbol_label": "FUNCTION"}},
            {"type": "DEFINES", "src": "file:src/b.c", "dst": "B_FN", "properties": {"symbol_label": "FUNCTION"}},
            {"type": "CALLS", "src": "A_FN", "dst": "B_FN", "properties": {}},
        ],
    }

    out_db = write_graph_sqlite(graph, tmp_path / "graph.db")
    conn = sqlite3.connect(str(out_db))
    conn.row_factory = sqlite3.Row
    try:
        node_a = conn.execute("SELECT file_path FROM nodes WHERE qualified_name='A_FN'").fetchone()
        node_b = conn.execute("SELECT file_path FROM nodes WHERE qualified_name='B_FN'").fetchone()
        call = conn.execute(
            "SELECT file_path FROM edges WHERE kind='CALLS' AND source_qualified='A_FN' AND target_qualified='B_FN'"
        ).fetchone()

        assert node_a is not None and node_a["file_path"] == "src/a.c"
        assert node_b is not None and node_b["file_path"] == "src/b.c"
        assert call is not None and call["file_path"] == "src/a.c"

        callers = get_callers(conn, "B_FN")
        assert len(callers) == 1
        assert callers[0]["caller_qn"] == "A_FN"
        assert callers[0]["file_path"] == "src/a.c"
    finally:
        conn.close()


def test_write_graph_sqlite_cross_file_calls_detectable(tmp_path: Path) -> None:
    graph = {
        "meta": {"project_path": "demo"},
        "nodes": [
            {"id": "file:src/a.c", "labels": ["FILE"], "properties": {"path": "src/a.c", "name": "a.c"}},
            {"id": "file:src/b.c", "labels": ["FILE"], "properties": {"path": "src/b.c", "name": "b.c"}},
            {"id": "A_FN", "labels": ["FUNCTION"], "properties": {"name": "a_fn", "kind": "FUNCTION"}},
            {"id": "B_FN", "labels": ["FUNCTION"], "properties": {"name": "b_fn", "kind": "FUNCTION"}},
        ],
        "edges": [
            {"type": "DEFINES", "src": "file:src/a.c", "dst": "A_FN", "properties": {"symbol_label": "FUNCTION"}},
            {"type": "DEFINES", "src": "file:src/b.c", "dst": "B_FN", "properties": {"symbol_label": "FUNCTION"}},
            {"type": "CALLS", "src": "A_FN", "dst": "B_FN", "properties": {}},
        ],
    }

    out_db = write_graph_sqlite(graph, tmp_path / "graph.db")
    conn = sqlite3.connect(str(out_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            WITH defs AS (
                SELECT target_qualified AS qn, substr(source_qualified, 6) AS fp
                FROM edges
                WHERE kind = 'DEFINES' AND source_qualified LIKE 'file:%'
            )
            SELECT COUNT(1) AS cross_file_calls
            FROM edges e
            LEFT JOIN nodes ns ON ns.qualified_name = e.source_qualified
            LEFT JOIN nodes nt ON nt.qualified_name = e.target_qualified
            LEFT JOIN defs ds ON ds.qn = e.source_qualified
            LEFT JOIN defs dt ON dt.qn = e.target_qualified
            WHERE e.kind = 'CALLS'
              AND COALESCE(ns.file_path, ds.fp, '') <> ''
              AND COALESCE(nt.file_path, dt.fp, '') <> ''
              AND lower(replace(COALESCE(ns.file_path, ds.fp, ''), '\\', '/'))
                  <> lower(replace(COALESCE(nt.file_path, dt.fp, ''), '\\', '/'))
            """
        ).fetchone()
        assert row is not None
        assert row["cross_file_calls"] == 1
    finally:
        conn.close()
