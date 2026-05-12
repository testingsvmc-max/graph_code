"""
Graph quality metrics for exported clangd-graph-rag artifacts.

Complements agent-style eval (e.g. GitNexus `eval/run_eval.py` + SWE-bench) with
deterministic checks on YAML/JSON exports and SQLite ``graph.db`` (graph-review–compatible schema).

Public API:
  - ``compute_metrics_from_export(graph: dict) -> dict``
  - ``compute_metrics_from_sqlite(db_path: Union[str, Path]) -> dict``
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Union


def _norm_fp(v: Any) -> str:
    if v is None:
        return ""
    return str(v).replace("\\", "/").strip()


def _lower_fp(fp: str) -> str:
    return _norm_fp(fp).lower()


def _file_paths_from_export(graph: Dict[str, Any]) -> Tuple[Dict[str, str], Set[Tuple[str, str]]]:
    """Map symbol id -> relative file path; also return set of (file:rel, id) DEFINES keys."""
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    qn_to_fp: Dict[str, str] = {}
    defines_pairs: Set[Tuple[str, str]] = set()

    for n in nodes:
        nid = n.get("id")
        if nid is None:
            continue
        nid_s = str(nid)
        props = n.get("properties") or {}
        fp = _norm_fp(props.get("file_path") or props.get("path"))
        if fp:
            qn_to_fp[nid_s] = fp

    for e in edges:
        if str(e.get("type") or "") != "DEFINES":
            continue
        src, dst = str(e.get("src") or ""), str(e.get("dst") or "")
        if src.startswith("file:") and dst:
            rel = _norm_fp(src[len("file:") :])
            if rel:
                qn_to_fp.setdefault(dst, rel)
                defines_pairs.add((src, dst))

    return qn_to_fp, defines_pairs


def compute_metrics_from_export(graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute coverage and call-graph metrics from an in-memory export dict
    (same shape as ``code_graph.yaml`` / ``GraphStore.load_graph_dict``).
    """
    nodes: List[Dict[str, Any]] = list(graph.get("nodes") or [])
    edges: List[Dict[str, Any]] = list(graph.get("edges") or [])
    node_ids = {str(n.get("id")) for n in nodes if n.get("id") is not None}

    qn_to_fp, _defines_pairs = _file_paths_from_export(graph)

    node_counts: Dict[str, int] = {}
    for n in nodes:
        for lb in n.get("labels") or []:
            k = str(lb)
            node_counts[k] = node_counts.get(k, 0) + 1

    edge_counts: Dict[str, int] = {}
    call_edges: List[Tuple[str, str]] = []
    for e in edges:
        et = str(e.get("type") or "")
        if not et:
            continue
        edge_counts[et] = edge_counts.get(et, 0) + 1
        if et == "CALLS":
            src, dst = str(e.get("src") or ""), str(e.get("dst") or "")
            if src and dst:
                call_edges.append((src, dst))

    cross_file = 0
    calls_both_files = 0
    calls_missing_src_fp = 0
    calls_missing_dst_fp = 0
    calls_unknown_endpoint = 0

    for src, dst in call_edges:
        if src not in node_ids or dst not in node_ids:
            calls_unknown_endpoint += 1
            continue
        sfp = qn_to_fp.get(src, "")
        dfp = qn_to_fp.get(dst, "")
        if sfp and dfp:
            calls_both_files += 1
            if _lower_fp(sfp) != _lower_fp(dfp):
                cross_file += 1
        if not sfp:
            calls_missing_src_fp += 1
        if not dfp:
            calls_missing_dst_fp += 1

    function_like_labels = {"FUNCTION", "METHOD"}
    fn_nodes = [n for n in nodes if set(n.get("labels") or []) & function_like_labels]
    fn_with_fp = sum(
        1
        for n in fn_nodes
        if _norm_fp((n.get("properties") or {}).get("file_path") or (n.get("properties") or {}).get("path"))
        or qn_to_fp.get(str(n.get("id")), "")
    )

    total_calls = len(call_edges)
    return {
        "source": "export_dict",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_counts_by_label": dict(sorted(node_counts.items())),
        "edge_counts_by_type": dict(sorted(edge_counts.items())),
        "calls": {
            "total": total_calls,
            "cross_file": cross_file,
            "cross_file_ratio": (cross_file / total_calls) if total_calls else 0.0,
            "with_both_endpoints_known": sum(1 for s, d in call_edges if s in node_ids and d in node_ids),
            "with_both_files": calls_both_files,
            "missing_caller_file_path": calls_missing_src_fp,
            "missing_callee_file_path": calls_missing_dst_fp,
            "unknown_endpoint_node": calls_unknown_endpoint,
        },
        "functions": {
            "labeled_function_or_method_nodes": len(fn_nodes),
            "with_resolved_file_path": fn_with_fp,
            "file_path_coverage_ratio": (fn_with_fp / len(fn_nodes)) if fn_nodes else 0.0,
        },
        "defines_edge_count": edge_counts.get("DEFINES", 0),
    }


def compute_metrics_from_sqlite(db_path: Union[str, Path]) -> Dict[str, Any]:
    """Same high-level metrics using SQLite ``nodes`` / ``edges`` tables."""
    db = Path(db_path).expanduser().resolve()
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        node_counts: Dict[str, int] = {}
        cur = conn.execute("SELECT kind, COUNT(1) n FROM nodes GROUP BY kind")
        for r in cur:
            node_counts[str(r["kind"] or "Unknown")] = int(r["n"])
        total_nodes = sum(node_counts.values())

        edge_counts: Dict[str, int] = {}
        cur = conn.execute("SELECT kind, COUNT(1) n FROM edges GROUP BY kind")
        for r in cur:
            edge_counts[str(r["kind"] or "")] = int(r["n"])

        sql = """
        WITH defs AS (
            SELECT target_qualified AS qn, substr(source_qualified, 6) AS fp
            FROM edges
            WHERE kind = 'DEFINES' AND source_qualified LIKE 'file:%'
        )
        SELECT
            COUNT(1) AS total_calls,
            SUM(
                CASE
                    WHEN COALESCE(ns.file_path, ds.fp, '') <> ''
                     AND COALESCE(nt.file_path, dt.fp, '') <> ''
                     AND lower(replace(COALESCE(ns.file_path, ds.fp, ''), '\\', '/'))
                         <> lower(replace(COALESCE(nt.file_path, dt.fp, ''), '\\', '/'))
                    THEN 1 ELSE 0
                END
            ) AS cross_file_calls,
            SUM(
                CASE
                    WHEN COALESCE(ns.file_path, ds.fp, '') <> ''
                     AND COALESCE(nt.file_path, dt.fp, '') <> ''
                    THEN 1 ELSE 0
                END
            ) AS calls_both_files,
            SUM(CASE WHEN COALESCE(ns.file_path, ds.fp, '') = '' THEN 1 ELSE 0 END) AS missing_caller_fp,
            SUM(CASE WHEN COALESCE(nt.file_path, dt.fp, '') = '' THEN 1 ELSE 0 END) AS missing_callee_fp
        FROM edges e
        LEFT JOIN nodes ns ON ns.qualified_name = e.source_qualified
        LEFT JOIN nodes nt ON nt.qualified_name = e.target_qualified
        LEFT JOIN defs ds ON ds.qn = e.source_qualified
        LEFT JOIN defs dt ON dt.qn = e.target_qualified
        WHERE e.kind = 'CALLS'
        """
        row = conn.execute(sql).fetchone()
        total_calls = int(row["total_calls"] or 0) if row else 0
        cross_file = int(row["cross_file_calls"] or 0) if row else 0
        both_files = int(row["calls_both_files"] or 0) if row else 0

        fn_row = conn.execute(
            "SELECT COUNT(1) n FROM nodes WHERE kind IN ('FUNCTION','METHOD','Function','Method')"
        ).fetchone()
        fn_total = int(fn_row["n"] or 0) if fn_row else 0
        fn_fp_row = conn.execute(
            "SELECT COUNT(1) n FROM nodes WHERE kind IN ('FUNCTION','METHOD','Function','Method') "
            "AND file_path <> ''"
        ).fetchone()
        fn_with_fp = int(fn_fp_row["n"] or 0) if fn_fp_row else 0

        return {
            "source": "sqlite",
            "db_path": str(db),
            "node_count": total_nodes,
            "edge_count": sum(edge_counts.values()),
            "node_counts_by_label": dict(sorted(node_counts.items())),
            "edge_counts_by_type": dict(sorted(edge_counts.items())),
            "calls": {
                "total": total_calls,
                "cross_file": cross_file,
                "cross_file_ratio": (cross_file / total_calls) if total_calls else 0.0,
                "with_both_files": both_files,
                "missing_caller_file_path": int(row["missing_caller_fp"] or 0) if row else 0,
                "missing_callee_file_path": int(row["missing_callee_fp"] or 0) if row else 0,
            },
            "functions": {
                "labeled_function_or_method_nodes": fn_total,
                "with_resolved_file_path": fn_with_fp,
                "file_path_coverage_ratio": (fn_with_fp / fn_total) if fn_total else 0.0,
            },
            "defines_edge_count": edge_counts.get("DEFINES", 0),
        }
    finally:
        conn.close()
