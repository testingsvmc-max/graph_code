#!/usr/bin/env python3
"""
Graph quality eval runner (YAML/JSON export or SQLite graph.db).

Unlike GitNexus ``eval/run_eval.py`` (SWE-bench + agent), this prints deterministic
metrics for regression tracking and CI gates.

Examples:
  python eval/run_graph_eval.py --yaml .clangd-graph-rag/code_graph.yaml
  python eval/run_graph_eval.py --db .clangd-graph-rag/graph.db --json-out eval/out.json
  python eval/run_graph_eval.py --yaml code_graph.yaml --min-cross-file-ratio 0.01
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code_graph_api.store import load_graph_dict
from eval.graph_metrics import compute_metrics_from_export, compute_metrics_from_sqlite


def main() -> int:
    p = argparse.ArgumentParser(description="clangd-graph-rag graph quality metrics")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--yaml", type=Path, help="Path to code_graph.yaml or .json export")
    g.add_argument("--db", type=Path, help="Path to SQLite graph.db")
    p.add_argument("--json-out", type=Path, default=None, help="Write full metrics JSON here")
    p.add_argument(
        "--min-cross-file-calls",
        type=int,
        default=None,
        help="Exit 2 if calls.cross_file is below this count",
    )
    p.add_argument(
        "--min-cross-file-ratio",
        type=float,
        default=None,
        help="Exit 2 if calls.cross_file_ratio is below this threshold (0..1)",
    )
    p.add_argument(
        "--min-function-file-path-coverage",
        type=float,
        default=None,
        help="Exit 2 if functions.file_path_coverage_ratio is below this (0..1)",
    )
    args = p.parse_args()

    if args.yaml is not None:
        path = args.yaml.expanduser().resolve()
        if not path.is_file():
            print(f"Not found: {path}", file=sys.stderr)
            return 2
        graph = load_graph_dict(str(path))
        metrics = compute_metrics_from_export(graph)
        metrics["input"] = {"kind": "yaml_or_json", "path": str(path)}
    else:
        path = args.db.expanduser().resolve()
        if not path.is_file():
            print(f"Not found: {path}", file=sys.stderr)
            return 2
        metrics = compute_metrics_from_sqlite(path)
        metrics["input"] = {"kind": "sqlite", "path": str(path)}

    text = json.dumps(metrics, indent=2, ensure_ascii=False, default=str)
    print(text)

    if args.json_out is not None:
        out = args.json_out.expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    calls = metrics.get("calls") or {}
    fn = metrics.get("functions") or {}

    if args.min_cross_file_calls is not None:
        if int(calls.get("cross_file") or 0) < args.min_cross_file_calls:
            print(
                f"FAIL: cross_file_calls {calls.get('cross_file')} < {args.min_cross_file_calls}",
                file=sys.stderr,
            )
            return 2

    if args.min_cross_file_ratio is not None:
        ratio = float(calls.get("cross_file_ratio") or 0.0)
        if ratio < args.min_cross_file_ratio:
            print(f"FAIL: cross_file_ratio {ratio} < {args.min_cross_file_ratio}", file=sys.stderr)
            return 2

    if args.min_function_file_path_coverage is not None:
        cov = float(fn.get("file_path_coverage_ratio") or 0.0)
        if cov < args.min_function_file_path_coverage:
            print(
                f"FAIL: function file_path coverage {cov} < {args.min_function_file_path_coverage}",
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
