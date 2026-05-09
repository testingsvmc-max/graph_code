"""Tests for eval/graph_metrics.py (GitNexus-style deterministic graph eval)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code_graph_export.sqlite_db import write_graph_sqlite
from eval.graph_metrics import compute_metrics_from_export, compute_metrics_from_sqlite


def test_compute_metrics_from_export_cross_file_and_coverage() -> None:
    graph = {
        "meta": {"project_path": "demo"},
        "nodes": [
            {"id": "file:src/a.c", "labels": ["FILE"], "properties": {"path": "src/a.c"}},
            {"id": "file:src/b.c", "labels": ["FILE"], "properties": {"path": "src/b.c"}},
            {"id": "A_FN", "labels": ["FUNCTION"], "properties": {"name": "a", "kind": "FUNCTION"}},
            {"id": "B_FN", "labels": ["FUNCTION"], "properties": {"name": "b", "kind": "FUNCTION"}},
        ],
        "edges": [
            {"type": "DEFINES", "src": "file:src/a.c", "dst": "A_FN", "properties": {}},
            {"type": "DEFINES", "src": "file:src/b.c", "dst": "B_FN", "properties": {}},
            {"type": "CALLS", "src": "A_FN", "dst": "B_FN", "properties": {}},
        ],
    }
    m = compute_metrics_from_export(graph)
    assert m["calls"]["total"] == 1
    assert m["calls"]["cross_file"] == 1
    assert m["calls"]["cross_file_ratio"] == 1.0
    assert m["calls"]["missing_caller_file_path"] == 0
    assert m["calls"]["missing_callee_file_path"] == 0
    assert m["functions"]["labeled_function_or_method_nodes"] == 2
    assert m["functions"]["with_resolved_file_path"] == 2
    assert m["functions"]["file_path_coverage_ratio"] == 1.0
    assert m["defines_edge_count"] == 2


def test_compute_metrics_from_export_same_file_call_not_cross_file() -> None:
    graph = {
        "meta": {},
        "nodes": [
            {"id": "X", "labels": ["FUNCTION"], "properties": {"file_path": "src/t.c"}},
            {"id": "Y", "labels": ["FUNCTION"], "properties": {"file_path": "src/t.c"}},
        ],
        "edges": [{"type": "CALLS", "src": "X", "dst": "Y", "properties": {}}],
    }
    m = compute_metrics_from_export(graph)
    assert m["calls"]["cross_file"] == 0
    assert m["calls"]["with_both_files"] == 1


def test_compute_metrics_from_sqlite_matches_fixture(tmp_path: Path) -> None:
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
    db = write_graph_sqlite(graph, tmp_path / "graph.db")
    m = compute_metrics_from_sqlite(db)
    assert m["source"] == "sqlite"
    assert m["calls"]["total"] >= 1
    assert m["calls"]["cross_file"] >= 1


def test_run_graph_eval_cli_yaml(tmp_path: Path) -> None:
    import subprocess

    graph = {
        "meta": {},
        "nodes": [{"id": "F", "labels": ["FUNCTION"], "properties": {"file_path": "a.c"}}],
        "edges": [],
    }
    y = tmp_path / "g.json"
    y.write_text(json.dumps(graph), encoding="utf-8")

    rc = subprocess.run(
        [sys.executable, str(_ROOT / "eval" / "run_graph_eval.py"), "--yaml", str(y)],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
    )
    assert rc.returncode == 0, rc.stderr
    out = json.loads(rc.stdout)
    assert out["node_count"] == 1
